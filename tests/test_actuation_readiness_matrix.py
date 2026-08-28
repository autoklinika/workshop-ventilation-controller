from __future__ import annotations

from dataclasses import replace
import unittest

from ventilation_core.domain.actuation_readiness import assess_actuation_readiness
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.shadow import (
    ShadowAutomationState,
    ShadowAutomationStatus,
    ShadowZoneProposal,
)
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1
from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState


AUTHORITY_BLOCKER = "ACTUATION_AUTHORITY_NOT_IMPLEMENTED"


def complete_tuning() -> ShadowOutputTuning:
    # Synthetic test values only. They are intentionally not production tuning.
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
        tacho_extract_fault_fallback_supply_pct=40.0,
        tacho_extract_fault_fallback_extract_pct=0.0,
        tacho_both_fault_fallback_supply_pct=0.0,
        tacho_both_fault_fallback_extract_pct=0.0,
    )


def monitor() -> TachoMonitorState:
    supply = FanTachoState("GPIO17", 17, 20.0, 400.0, 6, 0.01, True)
    extract = FanTachoState("GPIO27", 27, 20.0, 400.0, 6, 0.01, True)
    return TachoMonitorState("/dev/gpiochip0", True, True, None, supply, extract)


def base_shadow() -> ShadowAutomationState:
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
        control_reason="READINESS_MATRIX_TEST",
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
        control_reason="READINESS_MATRIX_TEST",
    )
    return ShadowAutomationState(
        enabled=True,
        actuation_supported=False,
        status=ShadowAutomationStatus.READY,
        evaluated_at_utc="2026-08-28T12:00:00+00:00",
        policy_version="readiness-matrix-test",
        zones=(zone1, zone2),
        tuning_complete=True,
        configuration_revision=2,
        configuration_persistent=True,
    )


def base_core() -> CoreState:
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=True,
        output_state_known=True,
        tacho=monitor(),
    )


class ActuationReadinessMatrixTests(unittest.TestCase):
    def assess(
        self,
        *,
        tuning: ShadowOutputTuning | None = None,
        core: CoreState | None = None,
        shadow: ShadowAutomationState | None = None,
    ):
        return assess_actuation_readiness(
            state=base_core() if core is None else core,
            shadow=base_shadow() if shadow is None else shadow,
            policy=ShadowPolicyV1(tuning=complete_tuning() if tuning is None else tuning),
        )

    def assert_fail_closed(self, assessment, expected_blocker: str) -> None:
        self.assertIn(expected_blocker, assessment.blockers)
        self.assertIn(AUTHORITY_BLOCKER, assessment.blockers)
        self.assertFalse(assessment.ready)
        self.assertFalse(assessment.actuation_authorized)

    def test_complete_preconditions_still_fail_closed_without_authority(self) -> None:
        assessment = self.assess()
        self.assertTrue(assessment.preconditions_satisfied)
        self.assertFalse(assessment.actuation_authorized)
        self.assertFalse(assessment.ready)
        self.assertEqual(assessment.blockers, (AUTHORITY_BLOCKER,))

    def test_each_configuration_prerequisite_has_its_own_blocker(self) -> None:
        cases = {
            "FAN_OUTPUT_TUNING_INCOMPLETE": dict(normal_air_request_pct=None),
            "AERO_OUTPUT_TUNING_INCOMPLETE": dict(aero_normal_speed=None),
            "DYNAMICS_TUNING_INCOMPLETE": dict(pm2_5_hysteresis_ug_m3=None),
            "FAN_SENSOR_FALLBACK_UNCONFIGURED": dict(
                sensor_fallback_supply_pct=None,
                sensor_fallback_extract_pct=None,
            ),
            "AERO_SENSOR_FALLBACK_UNCONFIGURED": dict(aero_sensor_fallback_speed=None),
            "TACHO_CONFIRMATION_UNCONFIGURED": dict(tacho_failure_confirmation_seconds=None),
            "TACHO_SUPPLY_FALLBACK_UNCONFIGURED": dict(
                tacho_supply_fault_fallback_supply_pct=None,
                tacho_supply_fault_fallback_extract_pct=None,
            ),
            "TACHO_EXTRACT_FALLBACK_UNCONFIGURED": dict(
                tacho_extract_fault_fallback_supply_pct=None,
                tacho_extract_fault_fallback_extract_pct=None,
            ),
            "TACHO_BOTH_FALLBACK_UNCONFIGURED": dict(
                tacho_both_fault_fallback_supply_pct=None,
                tacho_both_fault_fallback_extract_pct=None,
            ),
        }
        base = complete_tuning()
        for blocker, changes in cases.items():
            with self.subTest(blocker=blocker):
                assessment = self.assess(tuning=replace(base, **changes))
                self.assert_fail_closed(assessment, blocker)
                self.assertFalse(assessment.preconditions_satisfied)

    def test_each_runtime_prerequisite_has_its_own_blocker(self) -> None:
        healthy_core = base_core()
        healthy_shadow = base_shadow()
        cases = [
            (
                "CONTROL_ENGINE_CONFIG_NOT_PERSISTENT",
                healthy_core,
                replace(healthy_shadow, configuration_persistent=False),
            ),
            (
                "HARDWARE_NOT_READY",
                replace(healthy_core, hardware_ready=False),
                healthy_shadow,
            ),
            (
                "OUTPUT_STATE_UNKNOWN",
                replace(healthy_core, output_state_known=False),
                healthy_shadow,
            ),
            (
                "TACHO_MONITOR_UNAVAILABLE",
                replace(healthy_core, tacho=None),
                healthy_shadow,
            ),
            (
                "TACHO_MONITOR_UNAVAILABLE",
                replace(healthy_core, tacho=replace(monitor(), ready=False)),
                healthy_shadow,
            ),
            (
                "TACHO_MONITOR_UNAVAILABLE",
                replace(healthy_core, tacho=replace(monitor(), worker_alive=False)),
                healthy_shadow,
            ),
        ]
        for blocker, core_state, shadow_state in cases:
            with self.subTest(blocker=blocker, core=core_state):
                assessment = self.assess(core=core_state, shadow=shadow_state)
                self.assert_fail_closed(assessment, blocker)
                self.assertFalse(assessment.preconditions_satisfied)

    def test_every_non_ready_shadow_status_is_an_explicit_blocker(self) -> None:
        for status in ShadowAutomationStatus:
            if status == ShadowAutomationStatus.READY:
                continue
            with self.subTest(status=status):
                assessment = self.assess(shadow=replace(base_shadow(), status=status))
                self.assert_fail_closed(assessment, f"SHADOW_STATUS_{status.value}")
                self.assertFalse(assessment.preconditions_satisfied)

    def test_missing_zone1_is_explicit_and_fail_closed(self) -> None:
        base = base_shadow()
        without_zone1 = replace(base, zones=(base.zones[1],))
        assessment = self.assess(shadow=without_zone1)
        self.assert_fail_closed(assessment, "ZONE1_SHADOW_MISSING")
        self.assertFalse(assessment.preconditions_satisfied)

    def test_active_tacho_fault_and_fallback_are_independent_blockers(self) -> None:
        base = base_shadow()
        zone1 = base.zones[0]

        fault_only = replace(zone1, tacho_fault_pattern="SUPPLY", tacho_fallback_applied=False)
        assessment = self.assess(shadow=replace(base, zones=(fault_only, base.zones[1])))
        self.assert_fail_closed(assessment, "TACHO_FAULT_ACTIVE")
        self.assertNotIn("TACHO_FALLBACK_ACTIVE", assessment.blockers)

        fallback_only = replace(zone1, tacho_fault_pattern=None, tacho_fallback_applied=True)
        assessment = self.assess(shadow=replace(base, zones=(fallback_only, base.zones[1])))
        self.assert_fail_closed(assessment, "TACHO_FALLBACK_ACTIVE")
        self.assertNotIn("TACHO_FAULT_ACTIVE", assessment.blockers)

        both = replace(zone1, tacho_fault_pattern="BOTH", tacho_fallback_applied=True)
        assessment = self.assess(shadow=replace(base, zones=(both, base.zones[1])))
        self.assert_fail_closed(assessment, "TACHO_FAULT_ACTIVE")
        self.assertIn("TACHO_FALLBACK_ACTIVE", assessment.blockers)

    def test_authority_blocker_is_always_last_and_never_part_of_precondition_count(self) -> None:
        tuning = replace(complete_tuning(), normal_air_request_pct=None)
        state = replace(base_core(), hardware_ready=False)
        assessment = self.assess(tuning=tuning, core=state)

        self.assertEqual(assessment.blockers[-1], AUTHORITY_BLOCKER)
        self.assertIn("FAN_OUTPUT_TUNING_INCOMPLETE", assessment.blockers)
        self.assertIn("HARDWARE_NOT_READY", assessment.blockers)
        self.assertFalse(assessment.preconditions_satisfied)
        self.assertFalse(assessment.ready)


if __name__ == "__main__":
    unittest.main()
