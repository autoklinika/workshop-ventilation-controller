from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from ventilation_core.domain.aero import AeroBusState
from ventilation_core.domain.sensors import SensorBusState
from ventilation_core.domain.tacho import TachoMonitorState
from ventilation_core.domain.zigbee import ZigbeeMqttState


class VentilationMode(StrEnum):
    STOP = "STOP"
    MANUAL = "MANUAL"
    FAULT = "FAULT"


class AlarmCode(StrEnum):
    DAC_STATE_UNCERTAIN = "DAC_STATE_UNCERTAIN"
    DAC_COMMUNICATION_LOST = "DAC_COMMUNICATION_LOST"
    SENSOR_BUS_UNAVAILABLE = "SENSOR_BUS_UNAVAILABLE"
    SENSOR_NODE_UNAVAILABLE = "SENSOR_NODE_UNAVAILABLE"
    SENSOR_DATA_INVALID = "SENSOR_DATA_INVALID"
    SEN55_DIAGNOSTICS_UNAVAILABLE = "SEN55_DIAGNOSTICS_UNAVAILABLE"
    SEN55_FAN_SPEED_WARNING = "SEN55_FAN_SPEED_WARNING"
    SEN55_GAS_SENSOR_ERROR = "SEN55_GAS_SENSOR_ERROR"
    SEN55_RHT_ERROR = "SEN55_RHT_ERROR"
    SEN55_LASER_ERROR = "SEN55_LASER_ERROR"
    SEN55_FAN_ERROR = "SEN55_FAN_ERROR"
    AERO_BUS_UNAVAILABLE = "AERO_BUS_UNAVAILABLE"
    TACHO_MONITOR_UNAVAILABLE = "TACHO_MONITOR_UNAVAILABLE"
    TACHO_CONFIGURATION_INVALID = "TACHO_CONFIGURATION_INVALID"
    ZIGBEE_MQTT_DISCONNECTED = "ZIGBEE_MQTT_DISCONNECTED"
    ZIGBEE_BRIDGE_OFFLINE = "ZIGBEE_BRIDGE_OFFLINE"
    ZIGBEE_DEVICE_OFFLINE = "ZIGBEE_DEVICE_OFFLINE"
    ZIGBEE_DEVICE_DATA_STALE = "ZIGBEE_DEVICE_DATA_STALE"
    ZIGBEE_LOW_BATTERY = "ZIGBEE_LOW_BATTERY"


class AlarmSeverity(StrEnum):
    WARNING = "warning"
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
    alert_id: int | None = None
    source: str = "core"
    acknowledged_at: str | None = None

    @property
    def acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "code": self.code.value,
            "source": self.source,
            "severity": self.severity.value,
            "message": self.message,
            "active_since": self.active_since,
            "last_error": self.last_error,
            "occurrences": self.occurrences,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at,
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
    zigbee: ZigbeeMqttState | None = None

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
            "zigbee": None if self.zigbee is None else self.zigbee.to_dict(),
        }
