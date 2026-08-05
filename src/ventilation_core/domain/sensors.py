from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
from typing import Any


class SensorAvailability(IntFlag):
    PM1_0 = 1 << 0
    PM2_5 = 1 << 1
    PM4_0 = 1 << 2
    PM10_0 = 1 << 3
    HUMIDITY = 1 << 4
    TEMPERATURE = 1 << 5
    VOC = 1 << 6
    NOX = 1 << 7


class SensorNodeStatus(IntFlag):
    MEASUREMENT_VALID = 1 << 0
    SENSOR_PRESENT = 1 << 1
    MEASUREMENT_STALE = 1 << 2
    I2C_ERROR = 1 << 3
    DATA_ERROR = 1 << 4
    INITIALIZING = 1 << 5
    SENSOR_OFFLINE = 1 << 6
    PLATFORM_FAULT = 1 << 7


@dataclass(frozen=True)
class AirQualityReading:
    pm1_0_ug_m3: float | None = None
    pm2_5_ug_m3: float | None = None
    pm4_0_ug_m3: float | None = None
    pm10_0_ug_m3: float | None = None
    humidity_percent: float | None = None
    temperature_celsius: float | None = None
    voc_index: float | None = None
    nox_index: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "pm1_0_ug_m3": self.pm1_0_ug_m3,
            "pm2_5_ug_m3": self.pm2_5_ug_m3,
            "pm4_0_ug_m3": self.pm4_0_ug_m3,
            "pm10_0_ug_m3": self.pm10_0_ug_m3,
            "humidity_percent": self.humidity_percent,
            "temperature_celsius": self.temperature_celsius,
            "voc_index": self.voc_index,
            "nox_index": self.nox_index,
        }


@dataclass(frozen=True)
class SensorNodeState:
    slave_address: int
    online: bool = False
    usable: bool = False
    measurement_valid: bool = False
    measurement_stale: bool = True
    sensor_present: bool = False
    availability_mask: int = 0
    status_mask: int = 0
    reading: AirQualityReading = AirQualityReading()
    age_seconds: int | None = None
    sensor_errors: int = 0
    modbus_service_errors: int = 0
    uptime_seconds: int = 0
    firmware_version: str | None = None
    map_version: int | None = None
    sequence: int = 0
    last_success_at: str | None = None
    last_error: str | None = None
    polls: int = 0
    successful_polls: int = 0
    communication_errors: int = 0
    consecutive_failures: int = 0
    invalid_measurements: int = 0
    stale_measurements: int = 0
    map_version_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slave_address": self.slave_address,
            "online": self.online,
            "usable": self.usable,
            "measurement_valid": self.measurement_valid,
            "measurement_stale": self.measurement_stale,
            "sensor_present": self.sensor_present,
            "availability_mask": self.availability_mask,
            "status_mask": self.status_mask,
            "reading": self.reading.to_dict(),
            "age_seconds": self.age_seconds,
            "sensor_errors": self.sensor_errors,
            "modbus_service_errors": self.modbus_service_errors,
            "uptime_seconds": self.uptime_seconds,
            "firmware_version": self.firmware_version,
            "map_version": self.map_version,
            "sequence": self.sequence,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "polls": self.polls,
            "successful_polls": self.successful_polls,
            "communication_errors": self.communication_errors,
            "consecutive_failures": self.consecutive_failures,
            "invalid_measurements": self.invalid_measurements,
            "stale_measurements": self.stale_measurements,
            "map_version_errors": self.map_version_errors,
        }


@dataclass(frozen=True)
class SensorBusState:
    port: str
    baudrate: int
    addresses: tuple[int, ...]
    ready: bool = False
    worker_alive: bool = False
    worker_restarts: int = 0
    expected_map_version: int = 1
    inter_node_delay_seconds: float = 0.010
    poll_interval_seconds: float = 1.0
    last_cycle_at: str | None = None
    last_error: str | None = None
    nodes: tuple[SensorNodeState, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "addresses": list(self.addresses),
            "ready": self.ready,
            "worker_alive": self.worker_alive,
            "worker_restarts": self.worker_restarts,
            "expected_map_version": self.expected_map_version,
            "inter_node_delay_seconds": self.inter_node_delay_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "last_cycle_at": self.last_cycle_at,
            "last_error": self.last_error,
            "nodes": [node.to_dict() for node in self.nodes],
        }
