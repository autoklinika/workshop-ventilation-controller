from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from ventilation_core.application.control_engine_matrix import ControlEngineMatrixRunner


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config" / "control-engine-scenarios" / "lab-cross-domain-matrix-v1.json"

CALENDAR = {
    "inactive_off": (False, 0.0, 0.0),
    "inactive_standby": (False, 0.0, 0.0),
    "preventilation_auto": (True, 25.0, 30.0),
    "active_auto": (True, 30.0, 35.0),
    "purge_auto": (True, 20.0, 25.0),
    "active_fixed": (True, 55.0, 60.0),
}
AIR_REQUEST = {
    "normal": 20.0,
    "boost_voc": 40.0,
    "high_voc": 70.0,
    "max_voc": 100.0,
}
AIR_LEVEL = {
    "normal": "NORMAL",
    "boost_voc": "BOOST",
    "high_voc": "HIGH",
    "max_voc": "MAX",
}
THERMAL_LIMIT = {
    "normal": 100.0,
    "limiting": 60.0,
    "minimum": 30.0,
    "protection": 10.0,
}
THERMAL_BAND = {
    "normal": "NORMAL",
    "limiting": "LIMITING",
    "minimum": "MINIMUM",
    "protection": "PROTECTION",
}
SAFETY_FAULTS = {
    "critical_alarm",
    "output_unknown",
    "hardware_not_ready",
    "sensor1_loss_critical",
}
FAN_SENSOR_LOSS = {"sensor1_loss", "both_sensor_loss", "sensor1_loss_critical"}
AERO_SENSOR_LOSS = {"sensor2_loss", "both_sensor_loss"}
ZIGBEE_CONTEXT_FAULTS = {
    "zigbee_supply_stale": ("TEMPERATURE_STALE", True),
    "zigbee_supply_offline": ("ZIGBEE_DEVICE_OFFLINE", False),
}


def load_matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def zone(case: dict, address: int) -> dict:
    return next(
        row for row in case["shadow"]["zones"] if row["sensor_address"] == address
    )


class ControlEngineMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_matrix()
        cls.result = ControlEngineMatrixRunner().run(cls.payload).to_dict()

    def test_versioned_matrix_expands_expected_cartesian_product(self) -> None:
        self.assertEqual(self.result["policy_version"], "scenario-lab-only-v1")
        self.assertFalse(self.result["actuation_supported"])
        self.assertEqual(
            self.result["dimensions"],
            ["calendar", "air_quality", "temperature", "fault"],
        )
        self.assertEqual(self.result["case_count"], 6 * 4 * 4 * 10)
        self.assertEqual(len(self.result["cases"]), 960)
        self.assertEqual(
            len({case["case_id"] for case in self.result["cases"]}),
            960,
        )

    def test_every_case_remains_strictly_non_actuating(self) -> None:
        for case in self.result["cases"]:
            self.assertFalse(case["shadow"]["actuation_supported"], case["case_id"])
            for row in case["shadow"]["zones"]:
                self.assertIsNone(row["proposed_supply_voltage"], case["case_id"])
                self.assertIsNone(row["proposed_extract_voltage"], case["case_id"])

    def test_all_960_cases_follow_cross_domain_priority_rules(self) -> None:
        for case in self.result["cases"]:
            selected = case["selection"]
            calendar_id = selected["calendar"]
            aq_id = selected["air_quality"]
            temp_id = selected["temperature"]
            fault_id = selected["fault"]
            active, schedule_supply, schedule_extract = CALENDAR[calendar_id]
            fan = zone(case, 1)
            aero = zone(case, 2)

            if fault_id in SAFETY_FAULTS:
                self.assertEqual(
                    case["shadow"]["status"], "BLOCKED_SAFETY", case["case_id"]
                )
                for row in (fan, aero):
                    self.assertTrue(row["safety_override"], case["case_id"])
                    self.assertEqual(row["automation_state"], "FAULT", case["case_id"])
                    self.assertIsNone(row["final_supply_pct"], case["case_id"])
                    self.assertIsNone(row["final_extract_pct"], case["case_id"])
                    self.assertIsNone(row["proposed_aero_speed"], case["case_id"])
                continue

            if fault_id in FAN_SENSOR_LOSS:
                self.assertFalse(fan["sensor_usable"], case["case_id"])
                self.assertEqual(fan["automation_state"], "FAULT", case["case_id"])
                if active:
                    self.assertTrue(fan["sensor_fallback_applied"], case["case_id"])
                    self.assertEqual(
                        fan["final_supply_pct"],
                        max(schedule_supply, 45.0),
                        case["case_id"],
                    )
                    self.assertEqual(
                        fan["final_extract_pct"],
                        max(schedule_extract, 50.0),
                        case["case_id"],
                    )
                else:
                    self.assertFalse(fan["sensor_fallback_applied"], case["case_id"])
                    self.assertEqual(fan["final_supply_pct"], 0.0, case["case_id"])
                    self.assertEqual(fan["final_extract_pct"], 0.0, case["case_id"])
            else:
                self.assertTrue(fan["sensor_usable"], case["case_id"])
                self.assertEqual(
                    fan["air_quality_level"], AIR_LEVEL[aq_id], case["case_id"]
                )
                self.assertEqual(
                    fan["thermal_band"], THERMAL_BAND[temp_id], case["case_id"]
                )
                request = AIR_REQUEST[aq_id]
                if aq_id == "normal":
                    if not active:
                        expected_supply = 0.0
                        expected_extract = 0.0
                    else:
                        limit = THERMAL_LIMIT[temp_id]
                        expected_supply = min(max(schedule_supply, request), limit)
                        expected_extract = min(
                            max(schedule_extract, min(100.0, request + 5.0)),
                            min(100.0, limit + 5.0),
                        )
                    self.assertFalse(fan["air_quality_override"], case["case_id"])
                else:
                    expected_supply = max(schedule_supply, request)
                    expected_extract = max(
                        schedule_extract,
                        min(100.0, request + 5.0),
                    )
                    self.assertEqual(
                        fan["air_quality_override"],
                        temp_id != "normal",
                        case["case_id"],
                    )
                self.assertEqual(
                    fan["final_supply_pct"], expected_supply, case["case_id"]
                )
                self.assertEqual(
                    fan["final_extract_pct"], expected_extract, case["case_id"]
                )

            if fault_id in AERO_SENSOR_LOSS:
                self.assertFalse(aero["sensor_usable"], case["case_id"])
                self.assertEqual(aero["automation_state"], "FAULT", case["case_id"])
                if active:
                    self.assertTrue(aero["sensor_fallback_applied"], case["case_id"])
                    self.assertEqual(aero["proposed_aero_speed"], 2, case["case_id"])
                else:
                    self.assertFalse(aero["sensor_fallback_applied"], case["case_id"])
                    self.assertEqual(aero["proposed_aero_speed"], 0, case["case_id"])
            else:
                self.assertTrue(aero["sensor_usable"], case["case_id"])
                self.assertEqual(aero["air_quality_level"], "NORMAL", case["case_id"])
                self.assertEqual(aero["proposed_aero_speed"], 0, case["case_id"])

            if fault_id in ZIGBEE_CONTEXT_FAULTS:
                reason, stale = ZIGBEE_CONTEXT_FAULTS[fault_id]
                self.assertFalse(fan["outside_temperature_usable"], case["case_id"])
                self.assertEqual(
                    fan["outside_temperature_reason"], reason, case["case_id"]
                )
                self.assertEqual(
                    fan["outside_temperature_stale"], stale, case["case_id"]
                )
                self.assertIsNone(fan["temperature_delta_celsius"], case["case_id"])
            else:
                self.assertTrue(fan["outside_temperature_usable"], case["case_id"])
                self.assertEqual(fan["outside_temperature_reason"], "OK", case["case_id"])
                self.assertIsNotNone(fan["temperature_delta_celsius"], case["case_id"])

    def test_zigbee_context_faults_do_not_change_v1_control_request(self) -> None:
        cases = {
            tuple(case["selection"][name] for name in self.result["dimensions"]): case
            for case in self.result["cases"]
        }
        for calendar_id in CALENDAR:
            for aq_id in AIR_REQUEST:
                for temp_id in THERMAL_LIMIT:
                    baseline = zone(cases[(calendar_id, aq_id, temp_id, "none")], 1)
                    for fault_id in ZIGBEE_CONTEXT_FAULTS:
                        candidate = zone(cases[(calendar_id, aq_id, temp_id, fault_id)], 1)
                        candidate_case = cases[(calendar_id, aq_id, temp_id, fault_id)]
                        self.assertEqual(
                            candidate["final_supply_pct"],
                            baseline["final_supply_pct"],
                            candidate_case["case_id"],
                        )
                        self.assertEqual(
                            candidate["final_extract_pct"],
                            baseline["final_extract_pct"],
                            candidate_case["case_id"],
                        )
                        self.assertEqual(
                            candidate["automation_state"],
                            baseline["automation_state"],
                            candidate_case["case_id"],
                        )

    def test_selected_edge_cases_make_priority_semantics_explicit(self) -> None:
        by_selection = {
            tuple(case["selection"][name] for name in self.result["dimensions"]): case
            for case in self.result["cases"]
        }

        off_high_cold = zone(
            by_selection[("inactive_off", "high_voc", "protection", "none")], 1
        )
        self.assertEqual(off_high_cold["air_quality_level"], "HIGH")
        self.assertTrue(off_high_cold["air_quality_override"])
        self.assertEqual(off_high_cold["final_supply_pct"], 70.0)
        self.assertEqual(off_high_cold["final_extract_pct"], 75.0)

        active_cold_normal = zone(
            by_selection[("active_auto", "normal", "protection", "none")], 1
        )
        self.assertEqual(active_cold_normal["automation_state"], "TEMP_LIMIT")
        self.assertEqual(active_cold_normal["final_supply_pct"], 10.0)
        self.assertEqual(active_cold_normal["final_extract_pct"], 15.0)

        fixed_sensor_loss = zone(
            by_selection[("active_fixed", "max_voc", "protection", "sensor1_loss")], 1
        )
        self.assertTrue(fixed_sensor_loss["sensor_fallback_applied"])
        self.assertEqual(fixed_sensor_loss["final_supply_pct"], 55.0)
        self.assertEqual(fixed_sensor_loss["final_extract_pct"], 60.0)

        safety_over_fallback = zone(
            by_selection[
                ("active_auto", "max_voc", "protection", "sensor1_loss_critical")
            ],
            1,
        )
        self.assertTrue(safety_over_fallback["safety_override"])
        self.assertFalse(safety_over_fallback["sensor_fallback_applied"])
        self.assertIsNone(safety_over_fallback["final_supply_pct"])
        self.assertIsNone(safety_over_fallback["final_extract_pct"])

        stale_outside = zone(
            by_selection[("active_auto", "normal", "normal", "zigbee_supply_stale")],
            1,
        )
        self.assertEqual(stale_outside["outside_temperature_reason"], "TEMPERATURE_STALE")
        self.assertFalse(stale_outside["outside_temperature_usable"])
        self.assertIsNone(stale_outside["temperature_delta_celsius"])
        self.assertEqual(stale_outside["final_supply_pct"], 30.0)
        self.assertEqual(stale_outside["final_extract_pct"], 35.0)

    def test_matrix_contract_rejects_unsafe_or_ambiguous_definitions(self) -> None:
        unknown_step = deepcopy(self.payload)
        unknown_step["base_step"]["actuation_enabled"] = True
        with self.assertRaises(ValueError):
            ControlEngineMatrixRunner().run(unknown_step)

        timed_step = deepcopy(self.payload)
        timed_step["base_step"]["at_seconds"] = 0
        with self.assertRaises(ValueError):
            ControlEngineMatrixRunner().run(timed_step)

        duplicate_dimension = deepcopy(self.payload)
        duplicate_dimension["dimensions"][1]["name"] = "calendar"
        with self.assertRaises(ValueError):
            ControlEngineMatrixRunner().run(duplicate_dimension)

        duplicate_variant = deepcopy(self.payload)
        duplicate_variant["dimensions"][0]["variants"][1]["id"] = "inactive_off"
        with self.assertRaises(ValueError):
            ControlEngineMatrixRunner().run(duplicate_variant)

        with self.assertRaises(ValueError):
            ControlEngineMatrixRunner(max_cases=959).run(self.payload)


if __name__ == "__main__":
    unittest.main()
