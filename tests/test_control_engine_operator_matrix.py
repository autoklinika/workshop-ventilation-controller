from __future__ import annotations

import json
from pathlib import Path
import unittest

from ventilation_core.application.control_engine_matrix import ControlEngineMatrixRunner


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config" / "control-engine-scenarios" / "lab-operator-matrix-v1.json"

CALENDAR = {
    "inactive_off": (False, 0.0, 0.0),
    "active_auto": (True, 30.0, 35.0),
    "active_fixed": (True, 55.0, 60.0),
}
AIR = {
    "normal": ("NORMAL", 20.0, 0),
    "boost_voc": ("BOOST", 40.0, 1),
    "high_voc": ("HIGH", 70.0, 2),
    "max_voc": ("MAX", 100.0, 3),
}
SAFETY_FAULTS = {"critical_alarm", "output_unknown"}


def zone(case: dict, address: int) -> dict:
    return next(
        row for row in case["shadow"]["zones"] if row["sensor_address"] == address
    )


class ControlEngineOperatorMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(MATRIX.read_text(encoding="utf-8"))
        cls.result = ControlEngineMatrixRunner().run(payload).to_dict()
        cls.cases = {
            tuple(case["selection"][name] for name in cls.result["dimensions"]): case
            for case in cls.result["cases"]
        }

    def test_operator_matrix_expands_240_independent_cases(self) -> None:
        self.assertEqual(
            self.result["dimensions"],
            ["operator", "calendar", "air_quality", "temperature", "fault"],
        )
        self.assertEqual(self.result["case_count"], 2 * 3 * 4 * 2 * 5)
        self.assertEqual(len(self.result["cases"]), 240)
        self.assertEqual(len({case["case_id"] for case in self.result["cases"]}), 240)
        self.assertEqual(
            self.result["policy_version"], "scenario-operator-matrix-lab-only-v1"
        )

    def test_every_operator_case_is_strictly_non_actuating(self) -> None:
        self.assertFalse(self.result["actuation_supported"])
        for case in self.result["cases"]:
            self.assertFalse(case["shadow"]["actuation_supported"], case["case_id"])
            for item in case["shadow"]["zones"]:
                self.assertIsNone(item["proposed_supply_voltage"], case["case_id"])
                self.assertIsNone(item["proposed_extract_voltage"], case["case_id"])

    def test_all_240_cases_follow_operator_priority_contract(self) -> None:
        for case in self.result["cases"]:
            selected = case["selection"]
            operator_id = selected["operator"]
            calendar_id = selected["calendar"]
            aq_id = selected["air_quality"]
            temperature_id = selected["temperature"]
            fault_id = selected["fault"]
            active, schedule_supply, schedule_extract = CALENDAR[calendar_id]
            level, air_request, aero_request = AIR[aq_id]
            fan = zone(case, 1)
            aero = zone(case, 2)

            self.assertEqual(
                case["shadow"]["operator_mode"],
                "MANUAL" if operator_id == "manual_low" else "AUTO",
                case["case_id"],
            )

            if fault_id in SAFETY_FAULTS:
                self.assertEqual(
                    case["shadow"]["status"], "BLOCKED_SAFETY", case["case_id"]
                )
                for item in (fan, aero):
                    self.assertTrue(item["safety_override"], case["case_id"])
                    self.assertEqual(item["automation_state"], "FAULT", case["case_id"])
                    self.assertIsNone(item["final_supply_pct"], case["case_id"])
                    self.assertIsNone(item["final_extract_pct"], case["case_id"])
                    self.assertIsNone(item["proposed_aero_speed"], case["case_id"])
                if operator_id == "manual_low":
                    self.assertTrue(fan["operator_override"], case["case_id"])
                    self.assertEqual(
                        fan["operator_override_reason"],
                        "SAFETY_BLOCK_ACTIVE",
                        case["case_id"],
                    )
                continue

            if operator_id == "manual_low":
                self.assertEqual(fan["operator_manual_supply_pct"], 20.0, case["case_id"])
                self.assertEqual(fan["operator_manual_extract_pct"], 25.0, case["case_id"])
                self.assertEqual(aero["operator_manual_aero_speed"], 1, case["case_id"])

                if fault_id == "sensor1_loss":
                    self.assertEqual(fan["automation_state"], "FAULT", case["case_id"])
                    self.assertTrue(fan["sensor_fallback_applied"], case["case_id"])
                    self.assertEqual(fan["final_supply_pct"], 45.0, case["case_id"])
                    self.assertEqual(fan["final_extract_pct"], 50.0, case["case_id"])
                    self.assertTrue(fan["operator_override"], case["case_id"])
                    self.assertEqual(
                        fan["operator_override_reason"], "SENSOR_FALLBACK", case["case_id"]
                    )
                elif aq_id == "normal":
                    self.assertEqual(fan["automation_state"], "MANUAL", case["case_id"])
                    self.assertEqual(fan["final_supply_pct"], 20.0, case["case_id"])
                    self.assertEqual(fan["final_extract_pct"], 25.0, case["case_id"])
                    self.assertFalse(fan["operator_override"], case["case_id"])
                else:
                    expected_supply = max(20.0, air_request)
                    expected_extract = max(25.0, min(100.0, air_request + 5.0))
                    expected_state = "EMERGENCY_VENT" if aq_id == "max_voc" else "BOOST"
                    self.assertEqual(fan["automation_state"], expected_state, case["case_id"])
                    self.assertEqual(
                        fan["final_supply_pct"], expected_supply, case["case_id"]
                    )
                    self.assertEqual(
                        fan["final_extract_pct"], expected_extract, case["case_id"]
                    )
                    self.assertTrue(fan["operator_override"], case["case_id"])
                    self.assertEqual(
                        fan["operator_override_reason"],
                        f"AIR_QUALITY_{level}",
                        case["case_id"],
                    )

                # MANUAL is independent of Calendar and thermal energy saving.
                if fault_id != "sensor1_loss" and aq_id == "normal":
                    self.assertEqual(fan["final_supply_pct"], 20.0, case["case_id"])
                    self.assertEqual(fan["final_extract_pct"], 25.0, case["case_id"])
                    if temperature_id == "protection":
                        self.assertEqual(fan["temperature_limit_pct"], 10.0, case["case_id"])

                if aq_id == "normal":
                    self.assertEqual(aero["automation_state"], "MANUAL", case["case_id"])
                    self.assertEqual(aero["proposed_aero_speed"], 1, case["case_id"])
                    self.assertFalse(aero["operator_override"], case["case_id"])
                else:
                    expected_state = "EMERGENCY_VENT" if aq_id == "max_voc" else "BOOST"
                    self.assertEqual(aero["automation_state"], expected_state, case["case_id"])
                    self.assertEqual(
                        aero["proposed_aero_speed"], max(1, aero_request), case["case_id"]
                    )
                    self.assertTrue(aero["operator_override"], case["case_id"])
                continue

            # AUTO: retain the existing Calendar/AQ/thermal contract unchanged.
            self.assertEqual(fan["operator_mode"], "AUTO", case["case_id"])
            self.assertFalse(fan["operator_override"], case["case_id"])
            if fault_id == "sensor1_loss":
                self.assertEqual(fan["automation_state"], "FAULT", case["case_id"])
                if active:
                    self.assertEqual(
                        fan["final_supply_pct"], max(schedule_supply, 45.0), case["case_id"]
                    )
                    self.assertEqual(
                        fan["final_extract_pct"], max(schedule_extract, 50.0), case["case_id"]
                    )
                else:
                    self.assertEqual(fan["final_supply_pct"], 0.0, case["case_id"])
                    self.assertEqual(fan["final_extract_pct"], 0.0, case["case_id"])
            elif aq_id == "normal":
                if not active:
                    expected_supply, expected_extract = 0.0, 0.0
                else:
                    thermal_limit = 100.0 if temperature_id == "normal" else 10.0
                    expected_supply = min(max(schedule_supply, 20.0), thermal_limit)
                    expected_extract = min(
                        max(schedule_extract, 25.0),
                        min(100.0, thermal_limit + 5.0),
                    )
                self.assertEqual(fan["final_supply_pct"], expected_supply, case["case_id"])
                self.assertEqual(fan["final_extract_pct"], expected_extract, case["case_id"])
            else:
                self.assertEqual(
                    fan["final_supply_pct"], max(schedule_supply, air_request), case["case_id"]
                )
                self.assertEqual(
                    fan["final_extract_pct"],
                    max(schedule_extract, min(100.0, air_request + 5.0)),
                    case["case_id"],
                )

            self.assertEqual(aero["air_quality_level"], level, case["case_id"])
            if aq_id == "normal":
                self.assertEqual(aero["proposed_aero_speed"], 0, case["case_id"])
            else:
                self.assertEqual(
                    aero["proposed_aero_speed"], aero_request, case["case_id"]
                )

    def test_zigbee_stale_is_diagnostic_only_in_both_operator_modes(self) -> None:
        for operator_id in ("auto", "manual_low"):
            for calendar_id in CALENDAR:
                for aq_id in AIR:
                    for temperature_id in ("normal", "protection"):
                        baseline = self.cases[
                            (operator_id, calendar_id, aq_id, temperature_id, "none")
                        ]
                        stale = self.cases[
                            (
                                operator_id,
                                calendar_id,
                                aq_id,
                                temperature_id,
                                "zigbee_supply_stale",
                            )
                        ]
                        base_fan = zone(baseline, 1)
                        stale_fan = zone(stale, 1)
                        self.assertEqual(
                            stale_fan["final_supply_pct"],
                            base_fan["final_supply_pct"],
                            stale["case_id"],
                        )
                        self.assertEqual(
                            stale_fan["final_extract_pct"],
                            base_fan["final_extract_pct"],
                            stale["case_id"],
                        )
                        self.assertFalse(
                            stale_fan["outside_temperature_usable"], stale["case_id"]
                        )
                        self.assertEqual(
                            stale_fan["outside_temperature_reason"],
                            "TEMPERATURE_STALE",
                            stale["case_id"],
                        )
                        self.assertIsNone(
                            stale_fan["temperature_delta_celsius"], stale["case_id"]
                        )


if __name__ == "__main__":
    unittest.main()
