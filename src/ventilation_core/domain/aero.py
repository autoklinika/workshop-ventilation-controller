from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AeroTelemetry:
    humidity_percent: float | None = None
    supply_temperature_celsius: float | None = None
    extract_temperature_celsius: float | None = None
    outdoor_temperature_celsius: float | None = None
    fan_1_percent: int | None = None
    fan_2_percent: int | None = None

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "humidity_percent": self.humidity_percent,
            "supply_temperature_celsius": self.supply_temperature_celsius,
            "extract_temperature_celsius": self.extract_temperature_celsius,
            "outdoor_temperature_celsius": self.outdoor_temperature_celsius,
            "fan_1_percent": self.fan_1_percent,
            "fan_2_percent": self.fan_2_percent,
        }


@dataclass(frozen=True)
class AeroBusState:
    port: str
    baudrate: int
    slave_address: int
    register_addresses: tuple[int, ...]
    inter_register_delay_seconds: float
    poll_interval_seconds: float
    ready: bool = False
    worker_alive: bool = False
    worker_restarts: int = 0
    online: bool = False
    usable: bool = False
    telemetry: AeroTelemetry = AeroTelemetry()
    last_success_at: str | None = None
    last_cycle_at: str | None = None
    last_error: str | None = None
    polls: int = 0
    successful_polls: int = 0
    communication_errors: int = 0
    consecutive_failures: int = 0
    invalid_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "slave_address": self.slave_address,
            "register_addresses": list(self.register_addresses),
            "inter_register_delay_seconds": self.inter_register_delay_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "ready": self.ready,
            "worker_alive": self.worker_alive,
            "worker_restarts": self.worker_restarts,
            "online": self.online,
            "usable": self.usable,
            "telemetry": self.telemetry.to_dict(),
            "last_success_at": self.last_success_at,
            "last_cycle_at": self.last_cycle_at,
            "last_error": self.last_error,
            "polls": self.polls,
            "successful_polls": self.successful_polls,
            "communication_errors": self.communication_errors,
            "consecutive_failures": self.consecutive_failures,
            "invalid_samples": self.invalid_samples,
        }
