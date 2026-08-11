from __future__ import annotations

from collections.abc import Mapping

from ventilation_core.domain.aero import AeroTelemetry


HUMIDITY_REGISTER = 2016
SUPPLY_TEMPERATURE_REGISTER = 2021
EXTRACT_TEMPERATURE_REGISTER = 2022
OUTDOOR_TEMPERATURE_REGISTER = 2023
FAN_1_REGISTER = 2033
FAN_2_REGISTER = 2034

CONFIRMED_TELEMETRY_REGISTERS = (
    HUMIDITY_REGISTER,
    SUPPLY_TEMPERATURE_REGISTER,
    EXTRACT_TEMPERATURE_REGISTER,
    OUTDOOR_TEMPERATURE_REGISTER,
    FAN_1_REGISTER,
    FAN_2_REGISTER,
)


class AeroTelemetryError(ValueError):
    """Confirmed holding-register snapshot cannot be trusted as AERO telemetry."""


def _signed_16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def decode_aero_telemetry(registers: Mapping[int, int]) -> AeroTelemetry:
    missing = [
        address
        for address in CONFIRMED_TELEMETRY_REGISTERS
        if address not in registers
    ]
    if missing:
        raise AeroTelemetryError(
            "Missing confirmed AERO registers: " + ", ".join(map(str, missing))
        )
    if any(
        not 0 <= registers[address] <= 0xFFFF
        for address in CONFIRMED_TELEMETRY_REGISTERS
    ):
        raise AeroTelemetryError("AERO register value outside uint16 range")

    humidity_raw = registers[HUMIDITY_REGISTER]
    fan_1_raw = registers[FAN_1_REGISTER]
    fan_2_raw = registers[FAN_2_REGISTER]

    if humidity_raw > 1000:
        raise AeroTelemetryError(
            f"AERO humidity outside expected range: raw={humidity_raw}"
        )
    if fan_1_raw > 100 or fan_2_raw > 100:
        raise AeroTelemetryError(
            f"AERO fan power outside expected range: fan_1={fan_1_raw}, fan_2={fan_2_raw}"
        )

    temperatures = (
        _signed_16(registers[SUPPLY_TEMPERATURE_REGISTER]) / 10.0,
        _signed_16(registers[EXTRACT_TEMPERATURE_REGISTER]) / 10.0,
        _signed_16(registers[OUTDOOR_TEMPERATURE_REGISTER]) / 10.0,
    )
    if any(not -100.0 <= value <= 200.0 for value in temperatures):
        raise AeroTelemetryError(
            "AERO temperature outside expected engineering range: "
            + ", ".join(f"{value:.1f}" for value in temperatures)
        )

    return AeroTelemetry(
        humidity_percent=humidity_raw / 10.0,
        supply_temperature_celsius=temperatures[0],
        extract_temperature_celsius=temperatures[1],
        outdoor_temperature_celsius=temperatures[2],
        fan_1_percent=fan_1_raw,
        fan_2_percent=fan_2_raw,
    )
