from __future__ import annotations

import json
from pathlib import Path
import unittest

from ventilation_core.application.control_engine_scenario import ControlEngineScenarioRunner


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "config" / "control-engine-scenarios" / "lab-operator-v1.json"


def zone(step: dict, address: int) -> dict:
    return next(
        row for row in step["shadow"]["zones"] if row["sensor_address"] == address
    )


class ControlEngineOperatorScenarioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(SCENARIO.read_text(encoding="utf-8"))
        cls.result = ControlEngineScenarioRunner().run(payload).to_dict()

    def test_versioned_replay_remains_strictly_non_actuating(self) -> None:
        self.assertEqual(self.result["policy_version"], "scenario-operator-lab-only-v1")
        self.assertFalse(self.result["actuation_supported"])
        self.assertEqual(len(self.result["steps"]), 6)
        for step in self.result["steps"]:
            self.assertFalse(step["shadow"]["actuation_supported"])
            for row in step["shadow"]["zones"]:
                self.assertIsNone(row["proposed_supply_voltage"])
                self.assertIsNone(row["proposed_extract_voltage"])

    def test_auto_manual_safety_fallback_and_return_to_auto(self) -> None:
        steps = self.result["steps"]

        auto_initial = zone(steps[0], 1)
        self.assertEqual(steps[0]["operator_intent_revision"], 0)
        self.assertEqual(steps[0]["shadow"]["operator_mode"], "AUTO")
        self.assertEqual(auto_initial["automation_state"], "OFF")
        self.assertEqual(auto_initial["final_supply_pct"], 0.0)
        self.assertEqual(auto_initial["final_extract_pct"], 0.0)

        manual = zone(steps[1], 1)
        manual_aero = zone(steps[1], 2)
        self.assertEqual(steps[1]["operator_intent_revision"], 1)
        self.assertEqual(steps[1]["shadow"]["operator_mode"], "MANUAL")
        self.assertEqual(manual["automation_state"], "MANUAL")
        self.assertEqual(manual["final_supply_pct"], 20.0)
        self.assertEqual(manual["final_extract_pct"], 25.0)
        self.assertEqual(manual["temperature_limit_pct"], 10.0)
        self.assertFalse(manual["operator_override"])
        self.assertEqual(manual_aero["automation_state"], "MANUAL")
        self.assertEqual(manual_aero["proposed_aero_speed"], 1)

        high = zone(steps[2], 1)
        high_aero = zone(steps[2], 2)
        self.assertEqual(steps[2]["operator_intent_revision"], 1)
        self.assertEqual(high["air_quality_level"], "HIGH")
        self.assertEqual(high["automation_state"], "BOOST")
        self.assertEqual(high["final_supply_pct"], 70.0)
        self.assertEqual(high["final_extract_pct"], 75.0)
        self.assertTrue(high["operator_override"])
        self.assertEqual(high["operator_override_reason"], "AIR_QUALITY_HIGH")
        self.assertEqual(high_aero["proposed_aero_speed"], 2)
        self.assertTrue(high_aero["operator_override"])

        blocked = steps[3]
        self.assertEqual(blocked["shadow"]["status"], "BLOCKED_SAFETY")
        for address in (1, 2):
            item = zone(blocked, address)
            self.assertEqual(item["automation_state"], "FAULT")
            self.assertTrue(item["operator_override"])
            self.assertEqual(item["operator_override_reason"], "SAFETY_BLOCK_ACTIVE")
            self.assertIsNone(item["final_supply_pct"])
            self.assertIsNone(item["final_extract_pct"])
            self.assertIsNone(item["proposed_aero_speed"])

        fallback = zone(steps[4], 1)
        fallback_aero = zone(steps[4], 2)
        self.assertEqual(fallback["automation_state"], "FAULT")
        self.assertTrue(fallback["sensor_fallback_applied"])
        self.assertEqual(fallback["final_supply_pct"], 45.0)
        self.assertEqual(fallback["final_extract_pct"], 50.0)
        self.assertEqual(fallback_aero["proposed_aero_speed"], 2)

        returned = zone(steps[5], 1)
        self.assertEqual(steps[5]["operator_intent_revision"], 2)
        self.assertEqual(steps[5]["shadow"]["operator_mode"], "AUTO")
        self.assertIsNone(steps[5]["shadow"]["operator_manual_supply_pct"])
        self.assertFalse(returned["operator_override"])
        # Returning to AUTO must not erase Control Engine dynamics. HIGH was only
        # 30 seconds old, so the minimum-hold state remains authoritative.
        self.assertEqual(returned["air_quality_level"], "HIGH")
        self.assertEqual(returned["automation_state"], "BOOST")
        self.assertEqual(returned["final_supply_pct"], 70.0)
        self.assertEqual(returned["final_extract_pct"], 75.0)

    def test_replay_rejects_noncanonical_auto_operator_payload(self) -> None:
        payload = json.loads(SCENARIO.read_text(encoding="utf-8"))
        payload["steps"][1]["operator"] = {
            "mode": "AUTO",
            "manual_supply_pct": None,
        }
        with self.assertRaises(ValueError):
            ControlEngineScenarioRunner().run(payload)


if __name__ == "__main__":
    unittest.main()
