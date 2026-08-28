from __future__ import annotations

from dataclasses import replace
from typing import Callable
from datetime import datetime

from ventilation_core.domain.models import CoreState
from ventilation_core.domain.shadow import ShadowAutomationState, ShadowAutomationStatus
from ventilation_core.domain.shadow_policy import ShadowPolicyV1
from ventilation_core.domain.tacho_supervision import (
    TachoChannelSupervision,
    TachoFeedbackStatus,
    TachoSupervisionTracker,
)


class TachoShadowSupervisor:
    """Attach actual-output TACHO supervision to the non-actuating SHADOW state.

    Supervision uses authoritative *physical* EC voltage setpoints from CoreState,
    never the Control Engine proposal. This is essential while Control Engine is in
    SHADOW mode: proposed fan percentages must not make stopped physical fans look
    faulty.
    """

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._tracker = TachoSupervisionTracker(clock=clock)

    def apply(
        self,
        shadow: ShadowAutomationState,
        state: CoreState,
        policy: ShadowPolicyV1,
    ) -> ShadowAutomationState:
        if shadow.actuation_supported is not False:
            raise RuntimeError("TACHO supervisor received an actuating SHADOW state")

        supply, extract = self._tracker.evaluate(
            monitor=state.tacho,
            supply_voltage=state.setpoints.supply_voltage,
            extract_voltage=state.setpoints.extract_voltage,
            confirmation_seconds=policy.tuning.tacho_failure_confirmation_seconds,
        )

        zones = []
        tacho_requires_tuning = False
        tacho_fault = False
        for zone in shadow.zones:
            if zone.zone != "zone-1":
                zones.append(zone)
                continue

            zone = replace(
                zone,
                tacho_failure_confirmation_seconds=(
                    policy.tuning.tacho_failure_confirmation_seconds
                ),
                # Emergency action is intentionally not guessed before hardware
                # validation of channel-specific failure behavior.
                tacho_emergency_policy_configured=False,
                tacho_supply_feedback_required=supply.feedback_required,
                tacho_supply_status=supply.status.value,
                tacho_supply_feedback_valid=supply.feedback_valid,
                tacho_supply_rpm=supply.rpm,
                tacho_supply_pending_since_utc=supply.pending_since_utc,
                tacho_supply_fault_confirmed=supply.fault_confirmed,
                tacho_extract_feedback_required=extract.feedback_required,
                tacho_extract_status=extract.status.value,
                tacho_extract_feedback_valid=extract.feedback_valid,
                tacho_extract_rpm=extract.rpm,
                tacho_extract_pending_since_utc=extract.pending_since_utc,
                tacho_extract_fault_confirmed=extract.fault_confirmed,
            )

            tacho_requires_tuning = any(
                item.status == TachoFeedbackStatus.CONFIRMATION_TUNING_REQUIRED
                for item in (supply, extract)
            )
            tacho_fault = any(
                item.fault_confirmed
                or item.status
                in {
                    TachoFeedbackStatus.MONITOR_UNAVAILABLE,
                    TachoFeedbackStatus.CHANNEL_UNAVAILABLE,
                }
                for item in (supply, extract)
                if item.feedback_required
            )

            if tacho_fault:
                zone = replace(
                    zone,
                    automation_state="FAULT",
                    final_supply_pct=None,
                    final_extract_pct=None,
                    proposed_supply_voltage=None,
                    proposed_extract_voltage=None,
                    control_reason="TACHO_FEEDBACK_FAULT:EMERGENCY_POLICY_REQUIRED",
                )
            elif tacho_requires_tuning:
                zone = replace(
                    zone,
                    control_reason=(
                        f"{zone.control_reason}:TACHO_CONFIRMATION_TUNING_REQUIRED"
                    ),
                )
            zones.append(zone)

        if shadow.status == ShadowAutomationStatus.BLOCKED_SAFETY:
            status = shadow.status
        elif tacho_fault:
            status = ShadowAutomationStatus.DEGRADED
        elif tacho_requires_tuning and shadow.status == ShadowAutomationStatus.READY:
            status = ShadowAutomationStatus.TUNING_REQUIRED
        else:
            status = shadow.status

        return replace(shadow, status=status, zones=tuple(zones))


def tacho_summary(
    supervision: TachoChannelSupervision,
) -> dict[str, object]:
    """Small stable projection useful to tests and future diagnostics."""
    return supervision.to_dict()
