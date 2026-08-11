from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from ventilation_core.domain.aero import AeroBusState
from ventilation_core.domain.sensors import SensorBusState
from ventilation_core.domain.tacho import TachoMonitorState


class VentilationMode(StrEnum):
    STOP = "STOP"
    MANUAL = "MANUAL"
    FAULT = "FAULT"


class AlarmCode(StrEnum):
    DAC_COMMUNICATION_LOST = "DAC_COMMUNICATION_LOST"


class AlarmSeverity(StrEnum):
    CRITICAL = "critical"


@dataclass(frozen=True)
class FanSetpoints:
    supply_voltage: float
    extract_voltage: float

    @classmethod
    def stopped(cls) -> "FanSetpoints":
        return cls(0.0, 0.0)


@dataclass(frozen=True)
class AlarmState:
    code: AlarmCode
    severity: AlarmSeverity
    message: str
    active_since: str
    last_error: str
    occurrences: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "active_since": self.active_since,
            "last_error": self.last_error,
            "occurrences": self.occurrences,
        }


@dataclass(frozen=True)
class CoreState:
    mode: VentilationMode
    setpoints: FanSetpoints
    hardware_ready: bool
    output_state_known: bool = True
    consecutive_hardware_failures: int = 0
    active_alarms: tuple[AlarmState, ...] = ()
    sensor_bus: SensorBusState | None = None
    aero_bus: AeroBusState | None = None
    tacho: TachoMonitorState | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "setpoints": asdict(self.setpoints),
            "hardware_ready": self.hardware_ready,
            "output_state_known": self.output_state_known,
            "consecutive_hardware_failures": self.consecutive_hardware_failures,
            "active_alarms": [alarm.to_dict() for alarm in self.active_alarms],
            "sensor_bus": None if self.sensor_bus is None else self.sensor_bus.to_dict(),
            "aero_bus": None if self.aero_bus is None else self.aero_bus.to_dict(),
            "tacho": None if self.tacho is None else self.tacho.to_dict(),
        }
