from __future__ import annotations

from dataclasses import dataclass

from ventilation_core.domain.sensors import (
    AirQualityReading,
    SensorAvailability,
    SensorNodeStatus,
)


REGISTER_COUNT = 19
EXPECTED_MAP_VERSION = 1


class UnsupportedMapVersion(ValueError):
    def __init__(self, received: int, expected: int) -> None:
        self.received = received
        self.expected = expected
        super().__init__(
            f"Unsupported register map {received}; expected {expected}"
        )


@dataclass(frozen=True)
class DecodedSensorSample:
    reading: AirQualityReading
    availability_mask: int
    status_mask: int
    measurement_valid: bool
    measurement_stale: bool
    sensor_present: bool
    age_seconds: int | None
    sensor_errors: int
    modbus_service_errors: int
    uptime_seconds: int
    firmware_version: str
    map_version: int
    sequence: int
    sen55_device_status_supported: bool
    sen55_device_status_valid: bool
    sen55_fan_speed_warning: bool
    sen55_fan_cleaning: bool
    sen55_gas_sensor_error: bool
    sen55_rht_error: bool
    sen55_laser_error: bool
    sen55_fan_error: bool


def _signed_16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _combine_u32(high: int, low: int) -> int:
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def _optional_scaled(
    registers: list[int],
    index: int,
    mask: SensorAvailability,
    field: SensorAvailability,
    scale: float,
) -> float | None:
    return registers[index] / scale if mask & field else None


def decode_sensor_registers(
    registers: list[int],
    *,
    expected_map_version: int = EXPECTED_MAP_VERSION,
) -> DecodedSensorSample:
    if len(registers) != REGISTER_COUNT:
        raise ValueError(f"Expected {REGISTER_COUNT} registers, received {len(registers)}")

    map_version = registers[16]
    if map_version != expected_map_version:
        raise UnsupportedMapVersion(map_version, expected_map_version)

    availability = SensorAvailability(registers[8] & 0xFF)
    status = SensorNodeStatus(registers[9] & 0xFFFF)
    age = None if registers[10] == 0xFFFF else registers[10]
    firmware = registers[15]

    reading = AirQualityReading(
        pm1_0_ug_m3=_optional_scaled(registers, 0, availability, SensorAvailability.PM1_0, 10.0),
        pm2_5_ug_m3=_optional_scaled(registers, 1, availability, SensorAvailability.PM2_5, 10.0),
        pm4_0_ug_m3=_optional_scaled(registers, 2, availability, SensorAvailability.PM4_0, 10.0),
        pm10_0_ug_m3=_optional_scaled(registers, 3, availability, SensorAvailability.PM10_0, 10.0),
        humidity_percent=_optional_scaled(registers, 4, availability, SensorAvailability.HUMIDITY, 100.0),
        temperature_celsius=(
            _signed_16(registers[5]) / 100.0
            if availability & SensorAvailability.TEMPERATURE
            else None
        ),
        voc_index=_optional_scaled(registers, 6, availability, SensorAvailability.VOC, 10.0),
        nox_index=_optional_scaled(registers, 7, availability, SensorAvailability.NOX, 10.0),
    )
    stale = bool(status & SensorNodeStatus.MEASUREMENT_STALE)
    valid = bool(status & SensorNodeStatus.MEASUREMENT_VALID)
    valid = valid and bool(availability) and age is not None and not stale

    return DecodedSensorSample(
        reading=reading,
        availability_mask=int(availability),
        status_mask=int(status),
        measurement_valid=valid,
        measurement_stale=stale,
        sensor_present=bool(status & SensorNodeStatus.SENSOR_PRESENT),
        age_seconds=age,
        sensor_errors=registers[11],
        modbus_service_errors=registers[12],
        uptime_seconds=_combine_u32(registers[13], registers[14]),
        firmware_version=f"{(firmware >> 8) & 0xFF}.{firmware & 0xFF}",
        map_version=map_version,
        sequence=_combine_u32(registers[17], registers[18]),
        sen55_device_status_supported=bool(
            status & SensorNodeStatus.SEN55_DEVICE_STATUS_SUPPORTED
        ),
        sen55_device_status_valid=bool(
            status & SensorNodeStatus.SEN55_DEVICE_STATUS_VALID
        ),
        sen55_fan_speed_warning=bool(
            status & SensorNodeStatus.SEN55_FAN_SPEED_WARNING
        ),
        sen55_fan_cleaning=bool(status & SensorNodeStatus.SEN55_FAN_CLEANING),
        sen55_gas_sensor_error=bool(
            status & SensorNodeStatus.SEN55_GAS_SENSOR_ERROR
        ),
        sen55_rht_error=bool(status & SensorNodeStatus.SEN55_RHT_ERROR),
        sen55_laser_error=bool(status & SensorNodeStatus.SEN55_LASER_ERROR),
        sen55_fan_error=bool(status & SensorNodeStatus.SEN55_FAN_ERROR),
    )
