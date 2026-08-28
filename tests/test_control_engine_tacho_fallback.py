from __future__ import annotations

from dataclasses import replace
import unittest

from ventilation_core.application.control_engine_scenario import ControlEngineScenarioRunner
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1


SYNTHETIC_FALLBACKS = {
    "SUPPLY": (11.0, 61.0),
    "EXTRACT": (62.0, 12.0),
    "BOTH": (33.0, 44.0),
}


def tuning(*, with_fallbacks: bool = True) -> ShadowOutputTuning:
    values = dict(
        normal_air_request_pct=20.0,
        boost_air_request_pct=40.0,
        high_air_request_pct=70.0,
        max_air_request_pct=100.0,
        thermal_normal_limit_pct=100.0,
        thermal_limiting_limit_pct=60.0,
        thermal_minimum_limit_pct=30.0,
        thermal_protection_limit_pct=10.0,
        extract_bias_pct=5.0,
        aero_normal_speed=0,
        aero_boost_speed=1,
        aero_high_speed=2,
        aero_max_speed=3,
        pm2_5_hysteresis_ug_m3=2.0,
        voc_hysteresis_index=10.0,
        nox_hysteresis_index=5.0,
        temperature_hysteresis_celsius=1.0,
        pm2_5_boost_confirmation_seconds=30.0,
        state_minimum_hold_seconds=60.0,
        boost_decay_seconds=120.0,
        tacho_failure_confirmation_seconds=5.0,
    )
    if with_fallbacks:
        values.update(
            tacho_supply_fault_fallback_supply_pct=SYNTHETIC_FALLBACKS["SUPPLY"][0],
            tacho_supply_fault_fallback_extract_pct=SYNTHETIC_FALLBACKS["SUPPLY"][1],
            tacho_extract_fault_fallback_supply_pct=SYNTHETIC_FALLBACKS["EXTRACT"][0],
            tacho_extract_fault_fallback_extract_pct=SYNTHETIC_FALLBACKS["EXTRACT"][1],
            tacho_both_fault_fallback_supply_pct=SYNTHETIC_FALLBACKS["BOTH"][0],
            tacho_both_fault_fallback_extract_pct=SYNTHETIC_FALLBACKS["BOTH"][1],
        )
    return ShadowOutputTuning(**values)


def config(*, with_fallbacks: bool = True) -> dict:
    return ControlEngineConfig(
        policy=ShadowPolicyV1(
            version="synthetic-tacho-fallback-test-v1",
            tuning=tuning(with_fallbacks=with_fallbacks),
        )
    ).to_dict()


def sensor(*, usable: bool = True) -> dict:
    return {
        "usable": usable,
        "pm2_5_ug_m3": 5.0,
        "pm10_0_ug_m3": 8.0,
        "voc_index": 100.0,
        "nox_index": 1.0,
        "temperature_celsius": 22.0,
    }


def scenario_step(
    *,
    supply_voltage: float,
    extract_voltage: float,
    critical_alarm: bool = False,
    sensor_usable: bool = True,
) -> dict:
    return {
        "at_seconds": 0.0,
        "calendar": {
            "phase": "ACTIVE",
            "mode": "AUTO",
            "profile": "TACHO_FALLBACK_TEST",
            "schedule_supply_pct": 30.0,
            "schedule_extract_pct": 35.0,
            "schedule_request_source": "SCENARIO",
        },
        "actual_setpoints": {
            "supply_voltage": supply_voltage,
            "extract_voltage": extract_voltage,
        },
        # Deliberately omit TACHO monitor. A physically commanded channel must
        # therefore be classified immediately as MONITOR_UNAVAILABLE.
        "sensor_1": sensor(usable=sensor_usable),
        "sensor_2": sensor(),
        "critical_alarm": critical_alarm,
    }


def run_zone(step: dict, *, with_fallbacks: bool = True) -> tuple[dict, dict]:
    result = ControlEngineScenarioRunner().run(
        {
            "schema_version": 1,
            "name": "synthetic-tacho-fallback-case",
            "start_utc": "2026-01-15T08:00:00+00:00",
            "control_engine": config(with_fallbacks=with_fallbacks),
            "steps": [step],
        }
    ).to_dict()
    shadow = result["steps"][0]["shadow"]
    zone = next(item for item in shadow["zones"] if item["zone"] == "zone-1")
    return shadow, zone


class TachoFallbackContractTest(unittest.TestCase):
    def test_each_failure_mask_uses_only_its_exact_configured_pair(self) -> None:
        cases = (
            ("SUPPLY", 2.0, 0.0),
            ("EXTRACT", 0.0, 2.0),
            ("BOTH", 2.0, 2.0),
        )
        for mask, supply_voltage, extract_voltage in cases:
            with self.subTest(mask=mask):
                shadow, zone = run_zone(
                    scenario_step(
                        supply_voltage=supply_voltage,
                        extract_voltage=extract_voltage,
                    )
                )
                expected_supply, expected_extract = SYNTHETIC_FALLBACKS[mask]
                self.assertFalse(shadow["actuation_supported"])
                self.assertEqual(shadow["status"], "DEGRADED")
                self.assertEqual(zone["tacho_fault_pattern"], mask)
                self.assertTrue(zone["tacho_emergency_policy_configured"])
                self.assertTrue(zone["tacho_fallback_applied"])
                self.assertEqual(zone["tacho_fallback_supply_pct"], expected_supply)
                self.assertEqual(zone["tacho_fallback_extract_pct"], expected_extract)
                self.assertEqual(zone["final_supply_pct"], expected_supply)
                self.assertEqual(zone["final_extract_pct"], expected_extract)
                self.assertEqual(
                    zone["control_reason"],
                    f"TACHO_{mask}_FEEDBACK_FAULT:FALLBACK",
                )
                self.assertEqual(zone["automation_state"], "FAULT")
                self.assertIsNone(zone["proposed_supply_voltage"])
                self.assertIsNone(zone["proposed_extract_voltage"])

    def test_critical_safety_block_has_priority_over_configured_tacho_fallback(self) -> None:
        shadow, zone = run_zone(
            scenario_step(
                supply_voltage=2.0,
                extract_voltage=2.0,
                critical_alarm=True,
            )
        )
        self.assertEqual(shadow["status"], "BLOCKED_SAFETY")
        self.assertEqual(zone["tacho_fault_pattern"], "BOTH")
        self.assertTrue(zone["tacho_emergency_policy_configured"])
        self.assertFalse(zone["tacho_fallback_applied"])
        self.assertIsNone(zone["final_supply_pct"])
        self.assertIsNone(zone["final_extract_pct"])
        self.assertIsNone(zone["proposed_supply_voltage"])
        self.assertIsNone(zone["proposed_extract_voltage"])

    def test_tacho_fallback_does_not_mask_unavailable_base_control_context(self) -> None:
        shadow, zone = run_zone(
            scenario_step(
                supply_voltage=2.0,
                extract_voltage=2.0,
                sensor_usable=False,
            )
        )
        self.assertFalse(shadow["actuation_supported"])
        self.assertEqual(zone["tacho_fault_pattern"], "BOTH")
        self.assertTrue(zone["tacho_emergency_policy_configured"])
        self.assertFalse(zone["tacho_fallback_applied"])
        self.assertIsNone(zone["final_supply_pct"])
        self.assertIsNone(zone["final_extract_pct"])
        self.assertEqual(
            zone["control_reason"],
            "TACHO_BOTH_FEEDBACK_FAULT:FALLBACK_NOT_APPLIED_BASE_REQUEST_UNAVAILABLE",
        )

    def test_missing_tacho_fallback_never_invents_a_pair(self) -> None:
        shadow, zone = run_zone(
            scenario_step(supply_voltage=2.0, extract_voltage=0.0),
            with_fallbacks=False,
        )
        self.assertFalse(shadow["actuation_supported"])
        self.assertEqual(zone["tacho_fault_pattern"], "SUPPLY")
        self.assertFalse(zone["tacho_emergency_policy_configured"])
        self.assertFalse(zone["tacho_fallback_applied"])
        self.assertIsNone(zone["tacho_fallback_supply_pct"])
        self.assertIsNone(zone["tacho_fallback_extract_pct"])
        self.assertIsNone(zone["final_supply_pct"])
        self.assertIsNone(zone["final_extract_pct"])
        self.assertEqual(
            zone["control_reason"],
            "TACHO_SUPPLY_FEEDBACK_FAULT:EMERGENCY_POLICY_REQUIRED",
        )

    def test_partial_pair_configuration_is_rejected_for_each_failure_mask(self) -> None:
        base = tuning(with_fallbacks=False)
        mutations = (
            {"tacho_supply_fault_fallback_supply_pct": 10.0},
            {"tacho_extract_fault_fallback_extract_pct": 20.0},
            {"tacho_both_fault_fallback_supply_pct": 30.0},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(ValueError, "requires both supply and extract"):
                    replace(base, **mutation)


if __name__ == "__main__":
    unittest.main()
