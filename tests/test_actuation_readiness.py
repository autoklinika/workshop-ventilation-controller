from __future__ import annotations

from dataclasses import replace
import unittest

from ventilation_core.domain.actuation_readiness import assess_actuation_readiness
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.shadow import ShadowAutomationState, ShadowAutomationStatus, ShadowZoneProposal
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1
from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState


def complete_tuning() -> ShadowOutputTuning:
    return ShadowOutputTuning(
        normal_air_request_pct=25.0,
        boost_air_request_pct=45.0,
        high_air_request_pct=70.0,
        max_air_request_pct=100.0,
        thermal_normal_limit_pct=100.0,
        thermal_limiting_limit_pct=70.0,
        thermal_minimum_limit_pct=45.0,
        thermal_protection_limit_pct=25.0,
        extract_bias_pct=5.0,
        aero_normal_speed=1,
        aero_boost_speed=2,
        aero_high_speed=3,
        aero_max_speed=3,
        pm2_5_hysteresis_ug_m3=2.0,
        voc_hysteresis_index=10.0,
        nox_hysteresis_index=5.0,
        temperature_hysteresis_celsius=0.5,
        pm2_5_boost_confirmation_seconds=30.0,
        state_minimum_hold_seconds=60.0,
        boost_decay_seconds=120.0,
        sensor_fallback_supply_pct=30.0,
        sensor_fallback_extract_pct=35.0,
        aero_sensor_fallback_speed=1,
        tacho_failure_confirmation_seconds=4.0,
        tacho_supply_fault_fallback_supply_pct=0.0,
        tacho_supply_fault_fallback_extract_pct=40.0,
        tacho_extract_fault_fallback_supply_pct=0.0,
        tacho_extract_fault_fallback_extract_pct=0.0,
        tacho_both_fault_fallback_supply_pct=0.0,
        tacho_both_fault_fallback_extract_pct=0.0,
    )


def monitor() -> TachoMonitorState:
    supply = FanTachoState("GPIO17", 17, 20.0, 400.0, 6, 0.01, True)
    extract = FanTachoState("GPIO27", 27, 20.0, 400.0, 6, 0.01, True)
    return TachoMonitorState("/dev/gpiochip0", True, True, None, supply, extract)


def shadow() -> ShadowAutomationState:
    zone1 = ShadowZoneProposal(
        zone="zone-1",
        calendar_phase="ACTIVE",
        calendar_mode="AUTO",
        calendar_profile="NORMAL",
        sensor_address=1,
        sensor_usable=True,
        automation_state="NORMAL",
        final_supply_pct=30.0,
        final_extract_pct=35.0,
        tacho_failure_confirmation_seconds=4.0,
        tacho_supply_status="HEALTHY",
        tacho_extract_status="HEALTHY",
        control_reason="TEST",
    )
    zone2 = ShadowZoneProposal(
        zone="zone-2",
        calendar_phase="ACTIVE",
        calendar_mode="AUTO",
        calendar_profile="NORMAL",
        sensor_address=2,
        sensor_usable=True,
        automation_state="NORMAL",
        proposed_aero_speed=1,
        control_reason="TEST",
    )
    return ShadowAutomationState(
        enabled=True,
        actuation_supported=False,
        status=ShadowAutomationStatus.READY,
        evaluated_at_utc="2026-08-28T12:00:00+00:00",
        policy_version="test",
        zones=(zone1, zone2),
        tuning_complete=True,
        configuration_revision=2,
        configuration_persistent=True,
    )


def core() -> CoreState:
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=True,
        output_state_known=True,
        tacho=monitor(),
    )


class ActuationReadinessTests(unittest.TestCase):
    def test_complete_prerequisites_still_block_without_authority(self) -> None:
        assessment = assess_actuation_readiness(
            state=core(), shadow=shadow(), policy=ShadowPolicyV1(tuning=complete_tuning())
        )
        self.assertTrue(assessment.preconditions_satisfied)
        self.assertFalse(assessment.actuation_authorized)
        self.assertFalse(assessment.ready)
        self.assertEqual(assessment.blockers, ("ACTUATION_AUTHORITY_NOT_IMPLEMENTED",))

    def test_incomplete_tacho_emergency_policy_is_explicit(self) -> None:
        tuning = replace(
            complete_tuning(),
            tacho_supply_fault_fallback_supply_pct=None,
            tacho_supply_fault_fallback_extract_pct=None,
            tacho_extract_fault_fallback_supply_pct=None,
            tacho_extract_fault_fallback_extract_pct=None,
            tacho_both_fault_fallback_supply_pct=None,
            tacho_both_fault_fallback_extract_pct=None,
        )
        assessment = assess_actuation_readiness(
            state=core(), shadow=shadow(), policy=ShadowPolicyV1(tuning=tuning)
        )
        self.assertFalse(assessment.preconditions_satisfied)
        self.assertIn("TACHO_SUPPLY_FALLBACK_UNCONFIGURED", assessment.blockers)
        self.assertIn("TACHO_EXTRACT_FALLBACK_UNCONFIGURED", assessment.blockers)
        self.assertIn("TACHO_BOTH_FALLBACK_UNCONFIGURED", assessment.blockers)
        self.assertFalse(assessment.ready)

    def test_runtime_health_and_shadow_status_are_required(self) -> None:
        bad_state = replace(
            core(),
            hardware_ready=False,
            output_state_known=False,
            tacho=replace(monitor(), worker_alive=False),
        )
        bad_shadow = replace(shadow(), status=ShadowAutomationStatus.DEGRADED)
        assessment = assess_actuation_readiness(
            state=bad_state,
            shadow=bad_shadow,
            policy=ShadowPolicyV1(tuning=complete_tuning()),
        )
        for blocker in (
            "HARDWARE_NOT_READY",
            "OUTPUT_STATE_UNKNOWN",
            "TACHO_MONITOR_UNAVAILABLE",
            "SHADOW_STATUS_DEGRADED",
        ):
            self.assertIn(blocker, assessment.blockers)
        self.assertFalse(assessment.ready)

    def test_active_tacho_fault_and_fallback_block_readiness(self) -> None:
        base = shadow()
        zone1 = replace(base.zones[0], tacho_fault_pattern="SUPPLY", tacho_fallback_applied=True)
        assessment = assess_actuation_readiness(
            state=core(),
            shadow=replace(base, zones=(zone1, base.zones[1])),
            policy=ShadowPolicyV1(tuning=complete_tuning()),
        )
        self.assertIn("TACHO_FAULT_ACTIVE", assessment.blockers)
        self.assertIn("TACHO_FALLBACK_ACTIVE", assessment.blockers)
        self.assertFalse(assessment.ready)


if __name__ == "__main__":
    unittest.main()
