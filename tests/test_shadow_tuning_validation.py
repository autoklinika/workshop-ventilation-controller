from __future__ import annotations

import unittest

from ventilation_core.domain.shadow_policy import ShadowOutputTuning


class ShadowOutputTuningValidationTest(unittest.TestCase):
    def test_rejects_percentage_outside_command_range(self):
        with self.assertRaises(ValueError):
            ShadowOutputTuning(boost_air_request_pct=101.0)
        with self.assertRaises(ValueError):
            ShadowOutputTuning(extract_bias_pct=-0.1)

    def test_rejects_invalid_aero_speed(self):
        with self.assertRaises(ValueError):
            ShadowOutputTuning(aero_boost_speed=4)
        with self.assertRaises(ValueError):
            ShadowOutputTuning(aero_boost_speed=True)

    def test_rejects_negative_hysteresis_or_time(self):
        with self.assertRaises(ValueError):
            ShadowOutputTuning(voc_hysteresis_index=-1.0)
        with self.assertRaises(ValueError):
            ShadowOutputTuning(boost_decay_seconds=-1.0)

    def test_rejects_non_monotonic_air_requests(self):
        with self.assertRaises(ValueError):
            ShadowOutputTuning(
                normal_air_request_pct=30.0,
                boost_air_request_pct=70.0,
                high_air_request_pct=60.0,
                max_air_request_pct=100.0,
            )

    def test_rejects_non_monotonic_thermal_limits(self):
        with self.assertRaises(ValueError):
            ShadowOutputTuning(
                thermal_normal_limit_pct=100.0,
                thermal_limiting_limit_pct=50.0,
                thermal_minimum_limit_pct=60.0,
                thermal_protection_limit_pct=20.0,
            )

    def test_rejects_non_monotonic_aero_speeds(self):
        with self.assertRaises(ValueError):
            ShadowOutputTuning(
                aero_normal_speed=1,
                aero_boost_speed=3,
                aero_high_speed=2,
                aero_max_speed=3,
            )

    def test_fan_and_aero_outputs_can_be_tuned_independently(self):
        fan = ShadowOutputTuning(
            normal_air_request_pct=20.0,
            boost_air_request_pct=40.0,
            high_air_request_pct=70.0,
            max_air_request_pct=100.0,
            thermal_normal_limit_pct=100.0,
            thermal_limiting_limit_pct=70.0,
            thermal_minimum_limit_pct=40.0,
            thermal_protection_limit_pct=20.0,
            extract_bias_pct=5.0,
        )
        self.assertTrue(fan.fan_outputs_configured)
        self.assertFalse(fan.aero_outputs_configured)
        self.assertTrue(fan.outputs_configured)
        self.assertFalse(fan.complete)

        aero = ShadowOutputTuning(
            aero_normal_speed=0,
            aero_boost_speed=1,
            aero_high_speed=2,
            aero_max_speed=3,
        )
        self.assertFalse(aero.fan_outputs_configured)
        self.assertTrue(aero.aero_outputs_configured)
        self.assertTrue(aero.outputs_configured)
        self.assertFalse(aero.complete)


if __name__ == "__main__":
    unittest.main()
