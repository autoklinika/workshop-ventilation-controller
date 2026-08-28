import importlib.util
import json
import unittest
from pathlib import Path

from ventilation_core.domain.commissioning_candidate import CommissioningCandidate


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "control-engine-commissioning-candidate-template-v1.json"
TOOL = ROOT / "tools" / "control_engine_validate_commissioning_candidate.py"

spec = importlib.util.spec_from_file_location("candidate_tool", TOOL)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CommissioningCandidateTests(unittest.TestCase):
    def test_template_is_workshop_only_and_intentionally_incomplete(self) -> None:
        candidate = CommissioningCandidate.from_dict(
            json.loads(TEMPLATE.read_text(encoding="utf-8"))
        )
        self.assertEqual(candidate.environment, "WORKSHOP")
        self.assertFalse(candidate.complete_for_review)
        self.assertEqual(
            candidate.group("tacho_confirmation").value_dict()[
                "tacho_failure_confirmation_seconds"
            ],
            4.0,
        )
        self.assertEqual(candidate.group("tacho_confirmation").level.name, "PHYSICAL_VALIDATED")
        self.assertNotIn(
            "CANDIDATE_TACHO_CONFIRMATION_REQUIRES_PHYSICAL_VALIDATED",
            candidate.blockers(),
        )

    def test_all_unmeasured_workshop_values_remain_null(self) -> None:
        candidate = CommissioningCandidate.from_dict(
            json.loads(TEMPLATE.read_text(encoding="utf-8"))
        )
        flat = candidate.flatten_values()
        non_null = {name: value for name, value in flat.items() if value is not None}
        self.assertEqual(non_null, {"tacho_failure_confirmation_seconds": 4.0})

    def test_read_only_validator_reports_only_tacho_confirmation_completed(self) -> None:
        result = module.validate(TEMPLATE)
        self.assertFalse(result["complete_for_review"])
        self.assertEqual(result["completed_groups"], ["tacho_confirmation"])
        self.assertFalse(result["actuation_authority_granted"])
        self.assertFalse(result["writes_performed"])

    def test_candidate_rejects_lab_environment(self) -> None:
        payload = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        payload["environment"] = "LAB"
        with self.assertRaisesRegex(ValueError, "environment must be WORKSHOP"):
            CommissioningCandidate.from_dict(payload)

    def test_candidate_reuses_shadow_tuning_validation(self) -> None:
        payload = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        group = payload["groups"]["fan_outputs"]
        group["values"].update(
            {
                "normal_air_request_pct": 80.0,
                "boost_air_request_pct": 70.0,
                "high_air_request_pct": 60.0,
                "max_air_request_pct": 50.0,
                "thermal_normal_limit_pct": 100.0,
                "thermal_limiting_limit_pct": 80.0,
                "thermal_minimum_limit_pct": 60.0,
                "thermal_protection_limit_pct": 40.0,
                "extract_bias_pct": 0.0,
            }
        )
        with self.assertRaisesRegex(ValueError, "Air request percentages must be monotonic"):
            CommissioningCandidate.from_dict(payload)

    def test_validator_contains_no_application_or_actuator_path(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        for forbidden in (
            "control-engine-replace",
            "aero-speed",
            "aero-airing",
            "systemctl",
            "subprocess",
            "socket",
            "supply_voltage",
            "extract_voltage",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
