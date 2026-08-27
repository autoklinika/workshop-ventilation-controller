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

    automation_state: str | None = None
    schedule_supply_pct: float | None = None
    schedule_extract_pct: float | None = None
    schedule_request_source: str | None = None

    raw_air_quality_level: str | None = None
    raw_air_quality_driver: str | None = None
    air_quality_level: str | None = None
    air_quality_driver: str | None = None
    pm2_5_level: str | None = None
    voc_level: str | None = None
    nox_level: str | None = None
    pm10_reference_exceeded: bool | None = None
    air_quality_effective_since_utc: str | None = None
    dynamics_pending_level: str | None = None
    dynamics_pending_driver: str | None = None
    dynamics_pending_since_utc: str | None = None
    dynamics_transition_reason: str | None = None

    inside_temperature_celsius: float | None = None
    outside_temperature_celsius: float | None = None
    outside_temperature_usable: bool = False
    outside_temperature_stale: bool = False
    outside_temperature_age_seconds: float | None = None
    outside_temperature_source: str | None = None
    outside_temperature_reason: str | None = None
    temperature_delta_celsius: float | None = None
    raw_thermal_band: str | None = None
    thermal_band: str | None = None

    air_request_pct: float | None = None
    temperature_limit_pct: float | None = None
    final_supply_pct: float | None = None
    final_extract_pct: float | None = None

    sensor_fallback_applied: bool = False
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
            "automation_state": self.automation_state,
            "schedule_supply_pct": self.schedule_supply_pct,
            "schedule_extract_pct": self.schedule_extract_pct,
            "schedule_request_source": self.schedule_request_source,
            "raw_air_quality_level": self.raw_air_quality_level,
            "raw_air_quality_driver": self.raw_air_quality_driver,
            "air_quality_level": self.air_quality_level,
            "air_quality_driver": self.air_quality_driver,
            "pm2_5_level": self.pm2_5_level,
            "voc_level": self.voc_level,
            "nox_level": self.nox_level,
            "pm10_reference_exceeded": self.pm10_reference_exceeded,
            "air_quality_effective_since_utc": self.air_quality_effective_since_utc,
            "dynamics_pending_level": self.dynamics_pending_level,
            "dynamics_pending_driver": self.dynamics_pending_driver,
            "dynamics_pending_since_utc": self.dynamics_pending_since_utc,
            "dynamics_transition_reason": self.dynamics_transition_reason,
            "inside_temperature_celsius": self.inside_temperature_celsius,
            "outside_temperature_celsius": self.outside_temperature_celsius,
            "outside_temperature_usable": self.outside_temperature_usable,
            "outside_temperature_stale": self.outside_temperature_stale,
            "outside_temperature_age_seconds": self.outside_temperature_age_seconds,
            "outside_temperature_source": self.outside_temperature_source,
            "outside_temperature_reason": self.outside_temperature_reason,
            "temperature_delta_celsius": self.temperature_delta_celsius,
            "raw_thermal_band": self.raw_thermal_band,
            "thermal_band": self.thermal_band,
            "air_request_pct": self.air_request_pct,
            "temperature_limit_pct": self.temperature_limit_pct,
            "final_supply_pct": self.final_supply_pct,
            "final_extract_pct": self.final_extract_pct,
            "sensor_fallback_applied": self.sensor_fallback_applied,
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
