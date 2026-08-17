from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from ventilation_core.domain.zigbee import ZigbeeInventoryDevice, ZigbeeMqttState, ZigbeeTemperatureSensorState
from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeDeviceConfig
from ventilation_core.infrastructure.zigbee_reliable_monitor import ReliableZigbeeMqttMonitor
from ventilation_core.infrastructure.zigbee_role_store import SYSTEM_ROLES, ZigbeeRoleStore


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_UNASSIGNED_PREFIX = "__unassigned_"


def _is_assigned_config(config: ZigbeeDeviceConfig) -> bool:
    return bool(
        config.ieee_address
        and config.friendly_name
        and not config.friendly_name.startswith(_UNASSIGNED_PREFIX)
    )


class ManagedReliableZigbeeMqttMonitor(ReliableZigbeeMqttMonitor):
    """Reliable monitor with narrow rename and persistent semantic role management."""

    def __init__(self, config, *, role_store: ZigbeeRoleStore) -> None:
        self._role_store = role_store
        super().__init__(config)

    def state(self) -> ZigbeeMqttState:
        state = super().state()
        public_devices = tuple(
            device
            for device in state.devices
            if not device.friendly_name.startswith(_UNASSIGNED_PREFIX)
        )
        return replace(state, devices=public_devices)

    def rename_device(self, device_id: str, new_name: str) -> dict[str, Any]:
        device = self._resolve_inventory_device(device_id)
        if device.is_coordinator:
            raise ValueError("Zigbee coordinator cannot be renamed")
        new_name = self._validate_name(new_name)
        if new_name == device.friendly_name:
            return {
                "status": "ok",
                "data": {"from": device.friendly_name, "to": new_name, "unchanged": True},
            }
        with self._lock:
            if any(
                item.friendly_name == new_name and item.ieee_address != device.ieee_address
                for item in self._state.inventory
            ):
                raise ValueError(f"Zigbee friendly_name already exists: {new_name}")

        response = self._bridge_request(
            "device/rename",
            {"from": device.ieee_address, "to": new_name},
        )

        configs = list(self._config.devices)
        changed = False
        for index, config in enumerate(configs):
            if _is_assigned_config(config) and config.ieee_address == device.ieee_address:
                configs[index] = replace(config, friendly_name=new_name)
                changed = True
        if changed:
            self._apply_role_configs(tuple(configs), persist=True)
        return response

    def assign_role(self, device_id: str, role: str | None) -> dict[str, Any]:
        device = self._resolve_inventory_device(device_id)
        if device.is_coordinator:
            raise ValueError("Zigbee coordinator cannot receive a system role")
        if role is not None and role not in SYSTEM_ROLES:
            raise ValueError("Zigbee role must be supply, extract or null")

        configs = list(self._config.devices)
        current_index = next(
            (
                index
                for index, config in enumerate(configs)
                if _is_assigned_config(config) and config.ieee_address == device.ieee_address
            ),
            None,
        )

        if role is None:
            if current_index is not None:
                old_role = configs[current_index].role
                configs[current_index] = ZigbeeDeviceConfig(
                    role=old_role,
                    friendly_name=f"__unassigned_{old_role}__",
                    ieee_address=None,
                )
                self._apply_role_configs(tuple(configs), persist=True)
            return {
                "status": "ok",
                "data": {"id": device.ieee_address, "role": None},
            }

        target_index = next(index for index, config in enumerate(configs) if config.role == role)
        target = configs[target_index]
        if _is_assigned_config(target) and target.ieee_address != device.ieee_address:
            raise ValueError(
                f"System role {role} is already assigned to {target.friendly_name}; "
                "set that device to no role first"
            )

        # Ensure future telemetry for a system-role device survives core restarts.
        self._bridge_request(
            "device/options",
            {"id": device.ieee_address, "options": {"retain": True}},
        )

        if current_index is not None and current_index != target_index:
            old_role = configs[current_index].role
            configs[current_index] = ZigbeeDeviceConfig(
                role=old_role,
                friendly_name=f"__unassigned_{old_role}__",
                ieee_address=None,
            )
        configs[target_index] = ZigbeeDeviceConfig(
            role=role,
            friendly_name=device.friendly_name,
            ieee_address=device.ieee_address,
        )
        self._apply_role_configs(tuple(configs), persist=True)
        return {
            "status": "ok",
            "data": {
                "id": device.ieee_address,
                "friendly_name": device.friendly_name,
                "role": role,
                "retain": True,
            },
        }

    def remove_device(self, device_id: str) -> dict[str, Any]:
        device = self._resolve_inventory_device(device_id)
        response = super().remove_device(device.ieee_address)
        configs = list(self._config.devices)
        changed = False
        for index, config in enumerate(configs):
            if _is_assigned_config(config) and config.ieee_address == device.ieee_address:
                configs[index] = ZigbeeDeviceConfig(
                    role=config.role,
                    friendly_name=f"__unassigned_{config.role}__",
                    ieee_address=None,
                )
                changed = True
        if changed:
            self._apply_role_configs(tuple(configs), persist=True)
        return response

    def _handle_bridge_message(self, topic: str, raw_payload: bytes) -> None:
        super()._handle_bridge_message(topic, raw_payload)
        if topic == f"{self._state.base_topic}/bridge/devices":
            self._sync_assigned_names_from_inventory()

    def _sync_assigned_names_from_inventory(self) -> None:
        with self._lock:
            inventory = tuple(self._state.inventory)
            configs = tuple(self._config.devices)
        by_ieee = {device.ieee_address: device for device in inventory}
        updated: list[ZigbeeDeviceConfig] = []
        changed = False
        for config in configs:
            if not _is_assigned_config(config):
                updated.append(config)
                continue
            item = by_ieee.get(config.ieee_address or "")
            if item is not None and item.friendly_name != config.friendly_name:
                updated.append(replace(config, friendly_name=item.friendly_name))
                changed = True
            else:
                updated.append(config)
        if changed:
            self._apply_role_configs(tuple(updated), persist=True)

    def _apply_role_configs(
        self,
        configs: tuple[ZigbeeDeviceConfig, ...],
        *,
        persist: bool,
    ) -> None:
        base = self._state.base_topic
        with self._lock:
            old_topic_set = set(self._topic_to_role) | set(self._availability_to_role)
            old_states = tuple(self._devices.values())
            old_by_ieee = {
                device.ieee_address: device
                for device in old_states
                if device.ieee_address is not None
            }
            old_by_role = {device.role: device for device in old_states}

            new_devices: dict[str, ZigbeeTemperatureSensorState] = {}
            for config in configs:
                previous = (
                    old_by_ieee.get(config.ieee_address)
                    if config.ieee_address is not None
                    else old_by_role.get(config.role)
                )
                topic = f"{base}/{config.friendly_name}"
                if previous is None:
                    state = ZigbeeTemperatureSensorState(
                        role=config.role,
                        friendly_name=config.friendly_name,
                        ieee_address=config.ieee_address,
                        topic=topic,
                    )
                else:
                    state = replace(
                        previous,
                        role=config.role,
                        friendly_name=config.friendly_name,
                        ieee_address=config.ieee_address,
                        topic=topic,
                    )
                if not _is_assigned_config(config):
                    state = ZigbeeTemperatureSensorState(
                        role=config.role,
                        friendly_name=config.friendly_name,
                        ieee_address=None,
                        topic=topic,
                    )
                new_devices[config.role] = state

            self._config = replace(self._config, devices=configs)
            self._devices = new_devices
            self._topic_to_role = {
                device.topic: role for role, device in self._devices.items()
            }
            self._availability_to_role = {
                f"{device.topic}/availability": role for role, device in self._devices.items()
            }
            new_topic_set = set(self._topic_to_role) | set(self._availability_to_role)
            connected = self._state.connected is True
            self._state = replace(self._state, devices=self._ordered_devices())

        if persist:
            self._role_store.save_configs(configs)

        if connected:
            for topic in sorted(old_topic_set - new_topic_set):
                self._client.unsubscribe(topic)
            additions = sorted(new_topic_set - old_topic_set)
            if additions:
                self._client.subscribe([(topic, 0) for topic in additions])

    def _resolve_inventory_device(self, device_id: str) -> ZigbeeInventoryDevice:
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("Zigbee device id must be a non-empty string")
        needle = device_id.strip()
        with self._lock:
            matches = tuple(
                device
                for device in self._state.inventory
                if needle in {device.ieee_address, device.friendly_name}
            )
        if not matches:
            raise ValueError(f"Unknown Zigbee device: {needle}")
        return matches[0]

    @staticmethod
    def _validate_name(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Zigbee friendly_name must be a string")
        value = value.strip()
        if not _NAME_RE.fullmatch(value):
            raise ValueError(
                "Zigbee friendly_name must be 1..64 characters: letters, digits, '.', '_' or '-'"
            )
        if value.lower() == "bridge" or value.startswith(_UNASSIGNED_PREFIX):
            raise ValueError("Reserved Zigbee friendly_name")
        return value
