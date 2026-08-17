from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
        }
