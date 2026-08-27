from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ventilation_core.domain.shadow_dynamics import (
    AirQualityDynamicsTracker,
    ThermalDynamicsTracker,
)
from ventilation_core.domain.shadow_policy import (
    AirQualityLevel,
    ShadowOutputTuning,
    ShadowPolicyV1,
    ThermalBand,
)


def tuned_policy() -> ShadowPolicyV1:
    return ShadowPolicyV1(
        tuning=ShadowOutputTuning(
            normal_air_request_pct=30.0,
            boost_air_request_pct=50.0,
            high_air_request_pct=75.0,
            max_air_request_pct=100.0,
            thermal_normal_limit_pct=100.0,
            thermal_limiting_limit_pct=60.0,
            thermal_minimum_limit_pct=30.0,
            thermal_protection_limit_pct=15.0,
            extract_bias_pct=5.0,
            aero_normal_speed=1,
            aero_boost_speed=2,
            aero_high_speed=3,
            aero_max_speed=3,
            pm2_5_hysteresis_ug_m3=2.0,
            voc_hysteresis_index=10.0,
            nox_hysteresis_index=5.0,
            temperature_hysteresis_celsius=0.5,
            pm2_5_boost_confirmation_seconds=60.0,
            state_minimum_hold_seconds=120.0,
            boost_decay_seconds=180.0,
        )
    )


class AirQualityDynamicsTrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = tuned_policy()
        self.tracker = AirQualityDynamicsTracker()
        self.t0 = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)

    def update(self, seconds: float, *, pm: float, voc: float = 100.0, nox: float = 5.0):
        return self.tracker.update(
            self.policy,
            pm2_5_ug_m3=pm,
            voc_index=voc,
            nox_index=nox,
            now_utc=self.t0 + timedelta(seconds=seconds),
        )

    def test_initial_state_is_seeded_without_startup_delay(self) -> None:
        result = self.update(0, pm=30.0)
        self.assertEqual(result.raw_level, AirQualityLevel.HIGH)
        self.assertEqual(result.effective_level, AirQualityLevel.HIGH)
        self.assertEqual(result.transition_reason, "INITIALIZED")
        self.assertIsNone(result.pending_level)

    def test_pm2_5_boost_requires_configured_confirmation(self) -> None:
        initial = self.update(0, pm=10.0)
        self.assertEqual(initial.effective_level, AirQualityLevel.NORMAL)

        pending = self.update(10, pm=20.0)
        self.assertEqual(pending.raw_level, AirQualityLevel.BOOST)
        self.assertEqual(pending.effective_level, AirQualityLevel.NORMAL)
        self.assertEqual(pending.pending_level, AirQualityLevel.BOOST)
        self.assertEqual(pending.transition_reason, "ESCALATION_CONFIRMING")

        still_pending = self.update(69, pm=20.0)
        self.assertEqual(still_pending.effective_level, AirQualityLevel.NORMAL)

        confirmed = self.update(70, pm=20.0)
        self.assertEqual(confirmed.effective_level, AirQualityLevel.BOOST)
        self.assertEqual(confirmed.transition_reason, "ESCALATION_CONFIRMED")
        self.assertIsNone(confirmed.pending_level)

    def test_high_escalation_is_immediate_for_fail_safe_bias(self) -> None:
        self.update(0, pm=10.0)
        result = self.update(1, pm=30.0)
        self.assertEqual(result.effective_level, AirQualityLevel.HIGH)
        self.assertEqual(result.transition_reason, "ESCALATED_IMMEDIATELY")

    def test_metric_hysteresis_prevents_threshold_chatter(self) -> None:
        self.update(0, pm=20.0)
        # Initial BOOST is seeded immediately. 15 - 2 = 13 is the recovery edge.
        held = self.update(200, pm=14.0)
        self.assertEqual(held.raw_level, AirQualityLevel.NORMAL)
        self.assertEqual(held.effective_level, AirQualityLevel.BOOST)
        self.assertNotEqual(held.transition_reason, "DEESCALATION_DECAY")

        decay = self.update(201, pm=12.9)
        self.assertEqual(decay.effective_level, AirQualityLevel.BOOST)
        self.assertEqual(decay.pending_level, AirQualityLevel.NORMAL)
        self.assertEqual(decay.transition_reason, "DEESCALATION_DECAY")

        confirmed = self.update(381, pm=12.9)
        self.assertEqual(confirmed.effective_level, AirQualityLevel.NORMAL)
        self.assertEqual(confirmed.transition_reason, "DEESCALATION_CONFIRMED")

    def test_minimum_hold_precedes_decay(self) -> None:
        self.update(0, pm=30.0)
        held = self.update(60, pm=10.0)
        self.assertEqual(held.effective_level, AirQualityLevel.HIGH)
        self.assertEqual(held.transition_reason, "MINIMUM_HOLD")
        self.assertIsNone(held.pending_level)

        decay = self.update(121, pm=10.0)
        self.assertEqual(decay.effective_level, AirQualityLevel.HIGH)
        self.assertEqual(decay.pending_level, AirQualityLevel.NORMAL)
        self.assertEqual(decay.transition_reason, "DEESCALATION_DECAY")

    def test_incomplete_production_tuning_remains_transparent(self) -> None:
        tracker = AirQualityDynamicsTracker()
        policy = ShadowPolicyV1()
        first = tracker.update(
            policy,
            pm2_5_ug_m3=10.0,
            voc_index=100.0,
            nox_index=5.0,
            now_utc=self.t0,
        )
        second = tracker.update(
            policy,
            pm2_5_ug_m3=30.0,
            voc_index=100.0,
            nox_index=5.0,
            now_utc=self.t0 + timedelta(seconds=1),
        )
        self.assertEqual(first.effective_level, AirQualityLevel.NORMAL)
        self.assertEqual(second.effective_level, AirQualityLevel.HIGH)
        self.assertEqual(second.transition_reason, "DYNAMICS_TUNING_REQUIRED")


class ThermalDynamicsTrackerTest(unittest.TestCase):
    def test_cooling_is_immediate_but_recovery_uses_hysteresis(self) -> None:
        policy = tuned_policy()
        tracker = ThermalDynamicsTracker()

        raw, effective = tracker.update(policy, temperature_celsius=21.0)
        self.assertEqual((raw, effective), (ThermalBand.NORMAL, ThermalBand.NORMAL))

        raw, effective = tracker.update(policy, temperature_celsius=17.0)
        self.assertEqual(raw, ThermalBand.MINIMUM)
        self.assertEqual(effective, ThermalBand.MINIMUM)

        # Recovery edge from MINIMUM is 18.0 + 0.5 C.
        raw, effective = tracker.update(policy, temperature_celsius=18.2)
        self.assertEqual(raw, ThermalBand.LIMITING)
        self.assertEqual(effective, ThermalBand.MINIMUM)

        raw, effective = tracker.update(policy, temperature_celsius=18.5)
        self.assertEqual(raw, ThermalBand.LIMITING)
        self.assertEqual(effective, ThermalBand.LIMITING)

    def test_missing_dynamics_tuning_keeps_existing_stateless_classification(self) -> None:
        policy = ShadowPolicyV1()
        tracker = ThermalDynamicsTracker()
        _, first = tracker.update(policy, temperature_celsius=17.0)
        _, second = tracker.update(policy, temperature_celsius=18.1)
        self.assertEqual(first, ThermalBand.MINIMUM)
        self.assertEqual(second, ThermalBand.LIMITING)


if __name__ == "__main__":
    unittest.main()
