import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "control_engine_commissioning_status.py"
VALIDATION = ROOT / "config" / "control-engine-tuning-validation-v1.json"
PLAN = ROOT / "config" / "control-engine-commissioning-plan-v1.json"

spec = importlib.util.spec_from_file_location("control_engine_commissioning_status", TOOL)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ControlEngineCommissioningStatusTests(unittest.TestCase):
    def test_current_status_has_only_tacho_confirmation_complete(self) -> None:
        status = module.build_status(VALIDATION, PLAN)

        self.assertFalse(status["complete"])
        self.assertEqual(status["completed_groups"], ["tacho_confirmation"])
        self.assertEqual(
            set(status["pending_groups"]),
            {
                "fan_outputs",
                "aero_outputs",
                "dynamics",
                "fan_sensor_fallback",
                "aero_sensor_fallback",
                "tacho_supply_fallback",
                "tacho_extract_fallback",
                "tacho_both_fallback",
            },
        )
        self.assertFalse(status["actuation_authority_granted"])
        self.assertFalse(status["writes_performed"])

    def test_plan_requires_workshop_environment(self) -> None:
        payload = json.loads(PLAN.read_text(encoding="utf-8"))
        self.assertEqual(payload["environment_required"], "WORKSHOP")
        self.assertTrue(
            any("LAB environmental readings" in rule for rule in payload["rules"])
        )

    def test_each_group_contains_objective_observations_and_completion_criteria(self) -> None:
        payload = json.loads(PLAN.read_text(encoding="utf-8"))
        for name, group in payload["groups"].items():
            with self.subTest(group=name):
                self.assertIsInstance(group.get("objective"), str)
                self.assertTrue(group.get("required_observations"))
                self.assertTrue(group.get("completion_criteria"))

    def test_status_tool_is_read_only_by_contract(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        for forbidden in (
            "control-engine-replace",
            "aero-speed",
            "aero-airing",
            "supply_voltage",
            "extract_voltage",
            "systemctl",
            "subprocess",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
