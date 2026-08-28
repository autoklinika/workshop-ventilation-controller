from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ventilation_core.domain.models import CoreState
from ventilation_core.domain.shadow import ShadowAutomationState, ShadowAutomationStatus
from ventilation_core.domain.shadow_policy import ShadowPolicyV1


@dataclass(frozen=True)
class ActuationReadinessAssessment:
    """Diagnostic-only assessment of prerequisites for future actuation authority.

    `preconditions_satisfied` deliberately excludes the authority bit.  This lets the
    project prove that configuration and runtime prerequisites are complete while the
    Control Engine still has no actuator port.  `ready` can become true only if both
    the preconditions and explicit actuation authority are present.
    """

    preconditions_satisfied: bool
    actuation_authorized: bool
    ready: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "preconditions_satisfied": self.preconditions_satisfied,
            "actuation_authorized": self.actuation_authorized,
            "ready": self.ready,
            "blockers": list(self.blockers),
        }


def assess_actuation_readiness(
    *,
    state: CoreState,
    shadow: ShadowAutomationState,
    policy: ShadowPolicyV1,
) -> ActuationReadinessAssessment:
    """Return explicit blockers without granting any actuator capability."""

    blockers: list[str] = []
    tuning = policy.tuning

    if shadow.configuration_persistent is not True:
        blockers.append("CONTROL_ENGINE_CONFIG_NOT_PERSISTENT")

    if not tuning.fan_outputs_configured:
        blockers.append("FAN_OUTPUT_TUNING_INCOMPLETE")
    if not tuning.aero_outputs_configured:
        blockers.append("AERO_OUTPUT_TUNING_INCOMPLETE")
    if not tuning.dynamics_configured:
        blockers.append("DYNAMICS_TUNING_INCOMPLETE")

    if not tuning.fan_sensor_fallback_configured:
        blockers.append("FAN_SENSOR_FALLBACK_UNCONFIGURED")
    if not tuning.aero_sensor_fallback_configured:
        blockers.append("AERO_SENSOR_FALLBACK_UNCONFIGURED")

    if not tuning.tacho_confirmation_configured:
        blockers.append("TACHO_CONFIRMATION_UNCONFIGURED")
    if not tuning.tacho_supply_fault_fallback_configured:
        blockers.append("TACHO_SUPPLY_FALLBACK_UNCONFIGURED")
    if not tuning.tacho_extract_fault_fallback_configured:
        blockers.append("TACHO_EXTRACT_FALLBACK_UNCONFIGURED")
    if not tuning.tacho_both_fault_fallback_configured:
        blockers.append("TACHO_BOTH_FALLBACK_UNCONFIGURED")

    if state.hardware_ready is not True:
        blockers.append("HARDWARE_NOT_READY")
    if state.output_state_known is not True:
        blockers.append("OUTPUT_STATE_UNKNOWN")

    tacho = state.tacho
    if tacho is None or tacho.ready is not True or tacho.worker_alive is not True:
        blockers.append("TACHO_MONITOR_UNAVAILABLE")

    if shadow.status != ShadowAutomationStatus.READY:
        blockers.append(f"SHADOW_STATUS_{shadow.status.value}")

    zone1 = next((zone for zone in shadow.zones if zone.zone == "zone-1"), None)
    if zone1 is None:
        blockers.append("ZONE1_SHADOW_MISSING")
    else:
        if zone1.tacho_fault_pattern is not None:
            blockers.append("TACHO_FAULT_ACTIVE")
        if zone1.tacho_fallback_applied:
            blockers.append("TACHO_FALLBACK_ACTIVE")

    # Authority is intentionally checked last.  It is not part of the prerequisite
    # completeness calculation, but it is always required for final readiness.
    preconditions_satisfied = not blockers
    actuation_authorized = shadow.actuation_supported is True
    if not actuation_authorized:
        blockers.append("ACTUATION_AUTHORITY_NOT_IMPLEMENTED")

    ready = preconditions_satisfied and actuation_authorized
    return ActuationReadinessAssessment(
        preconditions_satisfied=preconditions_satisfied,
        actuation_authorized=actuation_authorized,
        ready=ready,
        blockers=tuple(blockers),
    )
