from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ShadowAutomationStatus(StrEnum):
    POLICY_UNCONFIGURED = "POLICY_UNCONFIGURED"
    BLOCKED_SAFETY = "BLOCKED_SAFETY"
    READY = "READY"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class ShadowZoneProposal:
    zone: str
    schedule_expectation: str
    sensor_address: int | None
    sensor_usable: bool
    air_request_pct: float | None = None
    temperature_limit_pct: float | None = None
    safety_override: bool = False
    proposed_supply_voltage: float | None = None
    proposed_extract_voltage: float | None = None
    proposed_aero_speed: int | None = None
    control_reason: str = "POLICY_NOT_CONFIGURED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "schedule_expectation": self.schedule_expectation,
            "sensor_address": self.sensor_address,
            "sensor_usable": self.sensor_usable,
            "air_request_pct": self.air_request_pct,
            "temperature_limit_pct": self.temperature_limit_pct,
            "safety_override": self.safety_override,
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
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "actuation_supported": self.actuation_supported,
            "status": self.status.value,
            "evaluated_at_utc": self.evaluated_at_utc,
            "policy_version": self.policy_version,
            "zones": [zone.to_dict() for zone in self.zones],
            "last_error": self.last_error,
        }
