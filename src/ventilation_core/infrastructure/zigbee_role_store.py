from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeDeviceConfig


SYSTEM_ROLES = ("supply", "extract")


@dataclass(frozen=True)
class ZigbeeRoleRecord:
    role: str
    ieee_address: str | None
    friendly_name: str | None

    @property
    def assigned(self) -> bool:
        return bool(self.ieee_address and self.friendly_name)


class ZigbeeRoleStore:
    """Small core-owned persistent registry for semantic Zigbee roles."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load_or_seed(
        self,
        defaults: tuple[ZigbeeDeviceConfig, ...],
    ) -> tuple[ZigbeeDeviceConfig, ...]:
        if not self._path.exists():
            by_role = {device.role: device for device in defaults}
            records = tuple(
                ZigbeeRoleRecord(
                    role=role,
                    ieee_address=(by_role[role].ieee_address if role in by_role else None),
                    friendly_name=(by_role[role].friendly_name if role in by_role else None),
                )
                for role in SYSTEM_ROLES
            )
            self.save_records(records)
            return self.to_runtime_configs(records)
        return self.to_runtime_configs(self.load_records())

    def load_records(self) -> tuple[ZigbeeRoleRecord, ...]:
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            raise ValueError("Unsupported Zigbee role registry version")
        roles = payload.get("roles")
        if not isinstance(roles, dict):
            raise ValueError("Zigbee role registry requires roles object")

        records: list[ZigbeeRoleRecord] = []
        for role in SYSTEM_ROLES:
            value = roles.get(role)
            if value is None:
                records.append(ZigbeeRoleRecord(role, None, None))
                continue
            if not isinstance(value, dict):
                raise ValueError(f"Invalid Zigbee role entry: {role}")
            ieee = value.get("ieee_address")
            name = value.get("friendly_name")
            if not isinstance(ieee, str) or not ieee.strip():
                raise ValueError(f"Invalid Zigbee IEEE for role: {role}")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Invalid Zigbee friendly_name for role: {role}")
            records.append(ZigbeeRoleRecord(role, ieee.strip(), name.strip()))
        return tuple(records)

    def save_configs(self, configs: tuple[ZigbeeDeviceConfig, ...]) -> None:
        by_role = {device.role: device for device in configs}
        records = tuple(
            ZigbeeRoleRecord(
                role=role,
                ieee_address=(by_role[role].ieee_address if role in by_role else None),
                friendly_name=(by_role[role].friendly_name if role in by_role else None),
            )
            for role in SYSTEM_ROLES
        )
        self.save_records(records)

    def save_records(self, records: tuple[ZigbeeRoleRecord, ...]) -> None:
        by_role = {record.role: record for record in records}
        payload = {
            "version": self.VERSION,
            "roles": {
                role: (
                    {
                        "ieee_address": by_role[role].ieee_address,
                        "friendly_name": by_role[role].friendly_name,
                    }
                    if role in by_role and by_role[role].assigned
                    else None
                )
                for role in SYSTEM_ROLES
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o660)
        os.replace(tmp, self._path)

    @staticmethod
    def to_runtime_configs(
        records: tuple[ZigbeeRoleRecord, ...],
    ) -> tuple[ZigbeeDeviceConfig, ...]:
        by_role = {record.role: record for record in records}
        configs: list[ZigbeeDeviceConfig] = []
        for role in SYSTEM_ROLES:
            record = by_role.get(role)
            if record is not None and record.assigned:
                configs.append(
                    ZigbeeDeviceConfig(
                        role=role,
                        friendly_name=record.friendly_name or "",
                        ieee_address=record.ieee_address,
                    )
                )
            else:
                # Base monitor requires a stable role entry. The managed monitor
                # filters these internal sentinels out of its public CoreState.
                configs.append(
                    ZigbeeDeviceConfig(
                        role=role,
                        friendly_name=f"__unassigned_{role}__",
                        ieee_address=None,
                    )
                )
        return tuple(configs)
