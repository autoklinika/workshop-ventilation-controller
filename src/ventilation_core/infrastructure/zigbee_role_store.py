from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeDeviceConfig


SYSTEM_ROLES = ("supply", "extract")
MULTI_ROLE = "other"


@dataclass(frozen=True)
class ZigbeeRoleRecord:
    role: str
    ieee_address: str | None
    friendly_name: str | None

    @property
    def assigned(self) -> bool:
        return bool(self.ieee_address and self.friendly_name)


class ZigbeeRoleStore:
    """Core-owned persistent registry for unique and multi-device Zigbee roles."""

    VERSION = 2

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
            self.save_assignments(self.to_runtime_configs(records), ())
            return self.to_runtime_configs(records)

        records, other = self._load_bundle()
        # Upgrade v1 registry in place without changing existing assignments.
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if payload.get("version") == 1:
            self.save_assignments(self.to_runtime_configs(records), other)
        return self.to_runtime_configs(records)

    def load_records(self) -> tuple[ZigbeeRoleRecord, ...]:
        return self._load_bundle()[0]

    def load_other_records(self) -> tuple[ZigbeeRoleRecord, ...]:
        return self._load_bundle()[1]

    def save_configs(self, configs: tuple[ZigbeeDeviceConfig, ...]) -> None:
        other = self.load_other_records() if self._path.exists() else ()
        self.save_assignments(configs, other)

    def save_other_records(self, records: tuple[ZigbeeRoleRecord, ...]) -> None:
        configs = self.to_runtime_configs(self.load_records())
        self.save_assignments(configs, records)

    def save_assignments(
        self,
        configs: tuple[ZigbeeDeviceConfig, ...],
        other_records: tuple[ZigbeeRoleRecord, ...],
    ) -> None:
        by_role = {device.role: device for device in configs}
        system_records = tuple(
            ZigbeeRoleRecord(
                role=role,
                ieee_address=(by_role[role].ieee_address if role in by_role else None),
                friendly_name=(by_role[role].friendly_name if role in by_role else None),
            )
            for role in SYSTEM_ROLES
        )
        self.save_records(system_records, other_records)

    def save_records(
        self,
        records: tuple[ZigbeeRoleRecord, ...],
        other_records: tuple[ZigbeeRoleRecord, ...] = (),
    ) -> None:
        by_role = {record.role: record for record in records}
        other_payload = []
        seen: set[str] = set()
        for record in other_records:
            if record.role != MULTI_ROLE or not record.assigned:
                continue
            ieee = record.ieee_address or ""
            if ieee in seen:
                continue
            seen.add(ieee)
            other_payload.append(
                {
                    "ieee_address": ieee,
                    "friendly_name": record.friendly_name,
                }
            )

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
            "other": other_payload,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o660)
        os.replace(tmp, self._path)

    def _load_bundle(
        self,
    ) -> tuple[tuple[ZigbeeRoleRecord, ...], tuple[ZigbeeRoleRecord, ...]]:
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") not in (1, self.VERSION):
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

        other_records: list[ZigbeeRoleRecord] = []
        raw_other = payload.get("other", []) if payload.get("version") == self.VERSION else []
        if not isinstance(raw_other, list):
            raise ValueError("Zigbee role registry other must be an array")
        for value in raw_other:
            if not isinstance(value, dict):
                raise ValueError("Invalid Zigbee OTHER role entry")
            ieee = value.get("ieee_address")
            name = value.get("friendly_name")
            if not isinstance(ieee, str) or not ieee.strip():
                raise ValueError("Invalid Zigbee IEEE for OTHER role")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Invalid Zigbee friendly_name for OTHER role")
            other_records.append(ZigbeeRoleRecord(MULTI_ROLE, ieee.strip(), name.strip()))
        return tuple(records), tuple(other_records)

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
                configs.append(
                    ZigbeeDeviceConfig(
                        role=role,
                        friendly_name=f"__unassigned_{role}__",
                        ieee_address=None,
                    )
                )
        return tuple(configs)
