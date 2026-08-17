from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
        }
