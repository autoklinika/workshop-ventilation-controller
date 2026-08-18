from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ZigbeeCapability:
    """A core-normalized value that a Zigbee device can publish in its state."""

    property: str
    name: str
    label: str
    value_type: str
    unit: str | None = None
    endpoint: str | None = None
    category: str | None = None
    description: str | None = None
    access: int = 1
    value_min: float | None = None
    value_max: float | None = None
    value_step: float | None = None
    values: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "property": self.property,
            "name": self.name,
            "label": self.label,
            "value_type": self.value_type,
            "unit": self.unit,
            "endpoint": self.endpoint,
            "category": self.category,
            "description": self.description,
            "access": self.access,
            "value_min": self.value_min,
            "value_max": self.value_max,
            "value_step": self.value_step,
            "values": list(self.values),
        }


@dataclass(frozen=True)
class ZigbeePairingState:
    """Core-owned state of the most recent pairing/interview workflow."""

    status: str
    ieee_address: str
    friendly_name: str
    event_at: str
    supported: bool | None = None
    model: str | None = None
    vendor: str | None = None
    description: str | None = None
    capabilities: tuple[ZigbeeCapability, ...] = ()
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ieee_address": self.ieee_address,
            "friendly_name": self.friendly_name,
            "event_at": self.event_at,
            "supported": self.supported,
            "model": self.model,
            "vendor": self.vendor,
            "description": self.description,
            "capabilities": [item.to_dict() for item in self.capabilities],
            "acknowledged": self.acknowledged,
        }


@dataclass(frozen=True)
class ZigbeeInventoryDevice:
    ieee_address: str
    friendly_name: str
    device_type: str
    supported: bool
    disabled: bool
    model: str | None = None
    vendor: str | None = None
    description: str | None = None
    power_source: str | None = None
    interview_state: str | None = None
    capabilities: tuple[ZigbeeCapability, ...] = ()

    @property
    def is_coordinator(self) -> bool:
        return self.device_type.lower() == "coordinator"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ieee_address": self.ieee_address,
            "friendly_name": self.friendly_name,
            "device_type": self.device_type,
            "supported": self.supported,
            "disabled": self.disabled,
            "model": self.model,
            "vendor": self.vendor,
            "description": self.description,
            "power_source": self.power_source,
            "interview_state": self.interview_state,
            "is_coordinator": self.is_coordinator,
            "capabilities": [item.to_dict() for item in self.capabilities],
        }


@dataclass(frozen=True)
class ZigbeeTemperatureSensorState:
    role: str
    friendly_name: str
    ieee_address: str | None
    topic: str
    available: bool | None = None
    temperature_celsius: float | None = None
    battery_percent: float | None = None
    linkquality: int | None = None
    last_seen: str | None = None
    last_message_at: str | None = None
    messages: int = 0
    parse_errors: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "friendly_name": self.friendly_name,
            "ieee_address": self.ieee_address,
            "topic": self.topic,
            "available": self.available,
            "temperature_celsius": self.temperature_celsius,
            "battery_percent": self.battery_percent,
            "linkquality": self.linkquality,
            "last_seen": self.last_seen,
            "last_message_at": self.last_message_at,
            "messages": self.messages,
            "parse_errors": self.parse_errors,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class ZigbeeSensorListItem:
    """Core-normalized telemetry row for every non-coordinator Zigbee device."""

    ieee_address: str
    friendly_name: str
    topic: str
    role: str | None = None
    model: str | None = None
    vendor: str | None = None
    available: bool | None = None
    temperature_celsius: float | None = None
    humidity_percent: float | None = None
    battery_percent: float | None = None
    voltage_mv: float | None = None
    linkquality: int | None = None
    last_seen: str | None = None
    last_message_at: str | None = None
    messages: int = 0
    parse_errors: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ieee_address": self.ieee_address,
            "friendly_name": self.friendly_name,
            "topic": self.topic,
            "role": self.role,
            "model": self.model,
            "vendor": self.vendor,
            "available": self.available,
            "temperature_celsius": self.temperature_celsius,
            "humidity_percent": self.humidity_percent,
            "battery_percent": self.battery_percent,
            "voltage_mv": self.voltage_mv,
            "linkquality": self.linkquality,
            "last_seen": self.last_seen,
            "last_message_at": self.last_message_at,
            "messages": self.messages,
            "parse_errors": self.parse_errors,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class ZigbeeMqttState:
    broker_host: str
    broker_port: int
    base_topic: str
    running: bool = False
    connected: bool = False
    connected_at: str | None = None
    disconnected_at: str | None = None
    last_message_at: str | None = None
    last_error: str | None = None
    devices: tuple[ZigbeeTemperatureSensorState, ...] = ()
    bridge_online: bool | None = None
    permit_join: bool | None = None
    permit_join_end: int | None = None
    inventory_updated_at: str | None = None
    last_event: dict[str, Any] | None = None
    inventory: tuple[ZigbeeInventoryDevice, ...] = ()
    pairing: ZigbeePairingState | None = None
    sensor_list: tuple[ZigbeeSensorListItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "base_topic": self.base_topic,
            "running": self.running,
            "connected": self.connected,
            "connected_at": self.connected_at,
            "disconnected_at": self.disconnected_at,
            "last_message_at": self.last_message_at,
            "last_error": self.last_error,
            "devices": [device.to_dict() for device in self.devices],
            "bridge_online": self.bridge_online,
            "permit_join": self.permit_join,
            "permit_join_end": self.permit_join_end,
            "inventory_updated_at": self.inventory_updated_at,
            "last_event": self.last_event,
            "inventory": [device.to_dict() for device in self.inventory],
            "pairing": None if self.pairing is None else self.pairing.to_dict(),
            "sensor_list": [item.to_dict() for item in self.sensor_list],
        }
