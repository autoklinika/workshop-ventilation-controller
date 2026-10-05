from __future__ import annotations

import unittest

from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState
from ventilation_core.domain.shadow import ShadowAutomationStatus
from ventilation_core.domain.shadow_policy import (
    AirQualityLevel,
    ShadowOutputTuning,
    ShadowPolicyV1,
    ThermalBand,
)


class ShadowPolicyV1ThresholdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ShadowPolicyV1()

    def test_policy_version_and_tuning_are_explicit(self):
        self.assertEqual(self.policy.version, "shadow-policy-v1-2026-08-12")
        self.assertFalse(self.policy.tuning.outputs_configured)
        self.assertFalse(self.policy.tuning.dynamics_configured)
        self.assertFalse(self.policy.tuning.complete)

    def test_pm2_5_uses_strict_process_thresholds_from_document(self):
        cases = (
            (15.0, AirQualityLevel.NORMAL),
            (15.01, AirQualityLevel.BOOST),
            (25.0, AirQualityLevel.BOOST),
            (25.01, AirQualityLevel.HIGH),
            (50.0, AirQualityLevel.HIGH),
            (50.01, AirQualityLevel.MAX),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.policy.classify_pm2_5(value), expected)

    def test_voc_uses_document_ranges(self):
        cases = (
            (149.99, AirQualityLevel.NORMAL),
            (150.0, AirQualityLevel.BOOST),
            (199.99, AirQualityLevel.BOOST),
            (200.0, AirQualityLevel.HIGH),
            (300.0, AirQualityLevel.HIGH),
            (300.01, AirQualityLevel.MAX),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.policy.classify_voc(value), expected)

    def test_nox_uses_strict_process_thresholds_from_document(self):
        cases = (
            (10.0, AirQualityLevel.NORMAL),
            (10.01, AirQualityLevel.BOOST),
            (50.0, AirQualityLevel.BOOST),
            (50.01, AirQualityLevel.HIGH),
            (100.0, AirQualityLevel.HIGH),
            (100.01, AirQualityLevel.MAX),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.policy.classify_nox(value), expected)

    def test_temperature_bands_match_document(self):
        cases = (
            (20.01, ThermalBand.NORMAL),
            (20.0, ThermalBand.LIMITING),
            (18.0, ThermalBand.LIMITING),
            (17.99, ThermalBand.MINIMUM),
            (16.0, ThermalBand.MINIMUM),
            (15.99, ThermalBand.PROTECTION),
            (None, ThermalBand.UNKNOWN),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.policy.classify_temperature(value), expected)

    def test_highest_air_quality_signal_wins_with_stable_driver_order(self):
        level, driver = self.policy.classify_air_quality(
            pm2_5_ug_m3=51.0,
            voc_index=301.0,
            nox_index=101.0,
        )
        self.assertEqual(level, AirQualityLevel.MAX)
        self.assertEqual(driver, "PM2_5")

    def test_pm10_reference_is_diagnostic_not_an_invented_stage_table(self):
        self.assertFalse(self.policy.pm10_reference_exceeded(45.0))
        self.assertTrue(self.policy.pm10_reference_exceeded(45.01))


class PolicyShadowAutomationEvaluatorTest(unittest.TestCase):
    def _state(
        self,
        *,
        zone1: AirQualityReading,
        zone2: AirQualityReading | None = None,
    ) -> CoreState:
        zone2 = zone2 or AirQualityReading(
            pm2_5_ug_m3=5.0,
            pm10_0_ug_m3=10.0,
            voc_index=100.0,
            nox_index=5.0,
            temperature_celsius=21.0,
        )
        calendar = CalendarResolution(
            available=True,
            timezone="Europe/Warsaw",
            evaluated_at_utc="2026-08-17T16:00:00+00:00",
            local_time="2026-08-17T18:00:00+02:00",
            phase=CalendarPhase.ACTIVE,
            effective_profile="NORMAL_WORKDAY",
            effective_mode=CalendarMode.AUTO,
            rule_id="MON_FRI",
        )
        nodes = (
            SensorNodeState(
                slave_address=1,
                online=True,
                usable=True,
                measurement_valid=True,
                measurement_stale=False,
                sensor_present=True,
                reading=zone1,
            ),
            SensorNodeState(
                slave_address=2,
                online=True,
                usable=True,
                measurement_valid=True,
                measurement_stale=False,
                sensor_present=True,
                reading=zone2,
            ),
        )
        sensor_bus = SensorBusState(
            port="/dev/ttyAMA0",
            baudrate=19200,
            addresses=(1, 2),
            ready=True,
            worker_alive=True,
            nodes=nodes,
        )
        return CoreState(
            mode=VentilationMode.STOP,
            setpoints=FanSetpoints.stopped(),
            hardware_ready=True,
            output_state_known=True,
            sensor_bus=sensor_bus,
            calendar=calendar,
        )

    def test_real_policy_classifies_but_production_tuning_stays_empty(self):
        state = self._state(
            zone1=AirQualityReading(
                pm2_5_ug_m3=10.0,
                pm10_0_ug_m3=20.0,
                voc_index=120.0,
                nox_index=5.0,
                temperature_celsius=19.0,
            )
        )
        result = PolicyShadowAutomationEvaluator(ShadowPolicyV1()).evaluate(state)

        self.assertEqual(result.status, ShadowAutomationStatus.TUNING_REQUIRED)
        self.assertEqual(result.policy_version, "shadow-policy-v1-2026-08-12")
        self.assertFalse(result.tuning_complete)
        self.assertFalse(result.actuation_supported)

        zone1, zone2 = result.zones
        self.assertEqual(zone1.calendar_phase, "ACTIVE")
        self.assertEqual(zone1.calendar_mode, "AUTO")
        self.assertEqual(zone1.air_quality_level, "NORMAL")
        self.assertEqual(zone1.thermal_band, "LIMITING")
        self.assertEqual(zone1.control_reason, "THERMAL_LIMITING")
        self.assertIsNone(zone1.air_request_pct)
        self.assertIsNone(zone1.temperature_limit_pct)
        self.assertIsNone(zone1.final_supply_pct)
        self.assertIsNone(zone1.final_extract_pct)
        self.assertIsNone(zone1.proposed_supply_voltage)
        self.assertIsNone(zone1.proposed_extract_voltage)

        self.assertEqual(zone2.thermal_band, "NOT_APPLICABLE")
        self.assertIsNone(zone2.temperature_limit_pct)
        self.assertIsNone(zone2.proposed_aero_speed)

    def test_air_quality_overrides_low_temperature_classification(self):
        state = self._state(
            zone1=AirQualityReading(
                pm2_5_ug_m3=30.0,
                pm10_0_ug_m3=60.0,
                voc_index=120.0,
                nox_index=5.0,
                temperature_celsius=17.0,
            )
        )
        zone1 = PolicyShadowAutomationEvaluator(ShadowPolicyV1()).evaluate(state).zones[0]

        self.assertEqual(zone1.air_quality_level, "HIGH")
        self.assertEqual(zone1.air_quality_driver, "PM2_5")
        self.assertEqual(zone1.thermal_band, "MINIMUM")
        self.assertTrue(zone1.air_quality_override)
        self.assertEqual(zone1.control_reason, "LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE")
        self.assertTrue(zone1.pm10_reference_exceeded)

    def test_pm10_reference_exceedance_does_not_invent_missing_process_stage(self):
        state = self._state(
            zone1=AirQualityReading(
                pm2_5_ug_m3=10.0,
                pm10_0_ug_m3=60.0,
                voc_index=120.0,
                nox_index=5.0,
                temperature_celsius=21.0,
            )
        )
        zone1 = PolicyShadowAutomationEvaluator(ShadowPolicyV1()).evaluate(state).zones[0]
        self.assertEqual(zone1.air_quality_level, "NORMAL")
        self.assertTrue(zone1.pm10_reference_exceeded)

    def test_pm2_5_boost_exposes_missing_confirmation_tuning(self):
        state = self._state(
            zone1=AirQualityReading(
                pm2_5_ug_m3=20.0,
                pm10_0_ug_m3=20.0,
                voc_index=100.0,
                nox_index=5.0,
                temperature_celsius=21.0,
            )
        )
        zone1 = PolicyShadowAutomationEvaluator(ShadowPolicyV1()).evaluate(state).zones[0]
        self.assertEqual(zone1.air_quality_level, "BOOST")
        self.assertEqual(
            zone1.control_reason,
            "PM2_5_BOOST_CONFIRMATION_TUNING_REQUIRED",
        )

    def test_explicit_test_tuning_can_generate_shadow_percentages_without_actuation(self):
        tuning = ShadowOutputTuning(
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
        policy = ShadowPolicyV1(tuning=tuning)
        state = self._state(
            zone1=AirQualityReading(
                pm2_5_ug_m3=30.0,
                pm10_0_ug_m3=20.0,
                voc_index=120.0,
                nox_index=5.0,
                temperature_celsius=17.0,
            ),
            zone2=AirQualityReading(
                pm2_5_ug_m3=5.0,
                pm10_0_ug_m3=10.0,
                voc_index=170.0,
                nox_index=5.0,
                temperature_celsius=21.0,
            ),
        )
        result = PolicyShadowAutomationEvaluator(policy).evaluate(state)

        self.assertEqual(result.status, ShadowAutomationStatus.READY)
        self.assertTrue(result.tuning_complete)
        self.assertFalse(result.actuation_supported)

        zone1, zone2 = result.zones
        self.assertEqual(zone1.air_request_pct, 75.0)
        self.assertEqual(zone1.temperature_limit_pct, 30.0)
        self.assertEqual(zone1.final_supply_pct, 75.0)
        self.assertEqual(zone1.final_extract_pct, 80.0)
        self.assertTrue(zone1.air_quality_override)
        self.assertIsNone(zone1.proposed_supply_voltage)
        self.assertIsNone(zone1.proposed_extract_voltage)

        self.assertEqual(zone2.air_quality_level, "BOOST")
        self.assertEqual(zone2.proposed_aero_speed, 2)
        self.assertIsNone(zone2.final_supply_pct)
        self.assertIsNone(zone2.final_extract_pct)


if __name__ == "__main__":
    unittest.main()
