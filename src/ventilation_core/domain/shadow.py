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

    sensor_online: bool = False
    sensor_measurement_valid: bool = False
    sensor_measurement_stale: bool = True
    sensor_age_seconds: int | None = None
    sensor_last_success_at: str | None = None
    sensor_pm2_5_ug_m3: float | None = None
    sensor_pm10_0_ug_m3: float | None = None
    sensor_voc_index: float | None = None
    sensor_nox_index: float | None = None
    sensor_temperature_celsius: float | None = None

    automation_state: str | None = None
    schedule_supply_pct: float | None = None
    schedule_extract_pct: float | None = None
    schedule_request_source: str | None = None

    operator_mode: str = "AUTO"
    operator_manual_supply_pct: float | None = None
    operator_manual_extract_pct: float | None = None
    operator_manual_aero_speed: int | None = None
    operator_override: bool = False
    operator_override_reason: str | None = None

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

    tacho_failure_confirmation_seconds: float | None = None
    tacho_emergency_policy_configured: bool = False
    tacho_fault_pattern: str | None = None
    tacho_fallback_applied: bool = False
    tacho_fallback_supply_pct: float | None = None
    tacho_fallback_extract_pct: float | None = None
    tacho_supply_feedback_required: bool = False
    tacho_supply_status: str | None = None
    tacho_supply_feedback_valid: bool = False
    tacho_supply_rpm: float | None = None
    tacho_supply_pending_since_utc: str | None = None
    tacho_supply_fault_confirmed: bool = False
    tacho_extract_feedback_required: bool = False
    tacho_extract_status: str | None = None
    tacho_extract_feedback_valid: bool = False
    tacho_extract_rpm: float | None = None
    tacho_extract_pending_since_utc: str | None = None
    tacho_extract_fault_confirmed: bool = False

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
            "sensor_online": self.sensor_online,
            "sensor_measurement_valid": self.sensor_measurement_valid,
            "sensor_measurement_stale": self.sensor_measurement_stale,
            "sensor_age_seconds": self.sensor_age_seconds,
            "sensor_last_success_at": self.sensor_last_success_at,
            "sensor_pm2_5_ug_m3": self.sensor_pm2_5_ug_m3,
            "sensor_pm10_0_ug_m3": self.sensor_pm10_0_ug_m3,
            "sensor_voc_index": self.sensor_voc_index,
            "sensor_nox_index": self.sensor_nox_index,
            "sensor_temperature_celsius": self.sensor_temperature_celsius,
            "automation_state": self.automation_state,
            "schedule_supply_pct": self.schedule_supply_pct,
            "schedule_extract_pct": self.schedule_extract_pct,
            "schedule_request_source": self.schedule_request_source,
            "operator_mode": self.operator_mode,
            "operator_manual_supply_pct": self.operator_manual_supply_pct,
            "operator_manual_extract_pct": self.operator_manual_extract_pct,
            "operator_manual_aero_speed": self.operator_manual_aero_speed,
            "operator_override": self.operator_override,
            "operator_override_reason": self.operator_override_reason,
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
            "tacho_failure_confirmation_seconds": self.tacho_failure_confirmation_seconds,
            "tacho_emergency_policy_configured": self.tacho_emergency_policy_configured,
            "tacho_fault_pattern": self.tacho_fault_pattern,
            "tacho_fallback_applied": self.tacho_fallback_applied,
            "tacho_fallback_supply_pct": self.tacho_fallback_supply_pct,
            "tacho_fallback_extract_pct": self.tacho_fallback_extract_pct,
            "tacho_supply_feedback_required": self.tacho_supply_feedback_required,
            "tacho_supply_status": self.tacho_supply_status,
            "tacho_supply_feedback_valid": self.tacho_supply_feedback_valid,
            "tacho_supply_rpm": self.tacho_supply_rpm,
            "tacho_supply_pending_since_utc": self.tacho_supply_pending_since_utc,
            "tacho_supply_fault_confirmed": self.tacho_supply_fault_confirmed,
            "tacho_extract_feedback_required": self.tacho_extract_feedback_required,
            "tacho_extract_status": self.tacho_extract_status,
            "tacho_extract_feedback_valid": self.tacho_extract_feedback_valid,
            "tacho_extract_rpm": self.tacho_extract_rpm,
            "tacho_extract_pending_since_utc": self.tacho_extract_pending_since_utc,
            "tacho_extract_fault_confirmed": self.tacho_extract_fault_confirmed,
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
    configuration_revision: int | None = None
    configuration_persistent: bool = False
    operator_mode: str = "AUTO"
    operator_manual_supply_pct: float | None = None
    operator_manual_extract_pct: float | None = None
    operator_manual_aero_speed: int | None = None
    operator_intent_revision: int | None = None
    operator_intent_persistent: bool = False
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "actuation_supported": self.actuation_supported,
            "status": self.status.value,
            "evaluated_at_utc": self.evaluated_at_utc,
            "policy_version": self.policy_version,
            "tuning_complete": self.tuning_complete,
            "configuration_revision": self.configuration_revision,
            "configuration_persistent": self.configuration_persistent,
            "operator_mode": self.operator_mode,
            "operator_manual_supply_pct": self.operator_manual_supply_pct,
            "operator_manual_extract_pct": self.operator_manual_extract_pct,
            "operator_manual_aero_speed": self.operator_manual_aero_speed,
            "operator_intent_revision": self.operator_intent_revision,
            "operator_intent_persistent": self.operator_intent_persistent,
            "zones": [zone.to_dict() for zone in self.zones],
            "last_error": self.last_error,
        }
