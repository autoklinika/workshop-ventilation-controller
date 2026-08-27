from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ShadowAutomationStatus(StrEnum):
    POLICY_UNCONFIGURED = "POLICY_UNCONFIGURED"
    TUNING_REQUIRED = "TUNING_REQUIRED"
    BLOCKED_SAFETY = "BLOCKED_SAFETY"
    READY = "READY"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class ShadowZoneProposal:
    zone: str
    calendar_phase: str
    calendar_mode: str | None
    calendar_profile: str | None
    sensor_address: int | None
    sensor_usable: bool

    air_quality_level: str | None = None
    air_quality_driver: str | None = None
    pm2_5_level: str | None = None
    voc_level: str | None = None
    nox_level: str | None = None
    pm10_reference_exceeded: bool | None = None

    inside_temperature_celsius: float | None = None
    outside_temperature_celsius: float | None = None
    thermal_band: str | None = None

    air_request_pct: float | None = None
    temperature_limit_pct: float | None = None
    final_supply_pct: float | None = None
    final_extract_pct: float | None = None

    safety_override: bool = False
    air_quality_override: bool = False
    proposed_supply_voltage: float | None = None
    proposed_extract_voltage: float | None = None
    proposed_aero_speed: int | None = None
    control_reason: str = "POLICY_NOT_CONFIGURED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "calendar_phase": self.calendar_phase,
            "calendar_mode": self.calendar_mode,
            "calendar_profile": self.calendar_profile,
            "sensor_address": self.sensor_address,
            "sensor_usable": self.sensor_usable,
            "air_quality_level": self.air_quality_level,
            "air_quality_driver": self.air_quality_driver,
            "pm2_5_level": self.pm2_5_level,
            "voc_level": self.voc_level,
            "nox_level": self.nox_level,
            "pm10_reference_exceeded": self.pm10_reference_exceeded,
            "inside_temperature_celsius": self.inside_temperature_celsius,
            "outside_temperature_celsius": self.outside_temperature_celsius,
            "thermal_band": self.thermal_band,
            "air_request_pct": self.air_request_pct,
            "temperature_limit_pct": self.temperature_limit_pct,
            "final_supply_pct": self.final_supply_pct,
            "final_extract_pct": self.final_extract_pct,
            "safety_override": self.safety_override,
            "air_quality_override": self.air_quality_override,
            "proposed_supply_voltage": self.proposed_supply_voltage,
            "proposed_extract_voltage": self.proposed_extract_voltage,
            "proposed_aero_speed": self.proposed_aero_speed,
            "control_reason": self.control_reason,
        }


@dataclass(frozen=True)
class ShadowAutomationState:
    enabled: bool
    actuation_supported: bool
    status: ShadowAutomationStatus
    evaluated_at_utc: str
    policy_version: str | None
    zones: tuple[ShadowZoneProposal, ...]
    tuning_complete: bool = False
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "actuation_supported": self.actuation_supported,
            "status": self.status.value,
            "evaluated_at_utc": self.evaluated_at_utc,
            "policy_version": self.policy_version,
            "tuning_complete": self.tuning_complete,
            "zones": [zone.to_dict() for zone in self.zones],
            "last_error": self.last_error,
        }
