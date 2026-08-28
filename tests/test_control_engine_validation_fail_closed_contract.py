import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "src" / "ventilation_core" / "application" / "control_engine_runtime.py"
BOOTSTRAP = ROOT / "src" / "ventilation_core" / "application" / "control_engine_bootstrap.py"


class ControlEngineValidationFailClosedContractTests(unittest.TestCase):
    def test_runtime_does_not_silently_bind_repository_evidence_profile(self) -> None:
        tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "assess_actuation_readiness"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {item.arg for item in calls[0].keywords if item.arg is not None}
        self.assertNotIn("validation_profile", keywords)

    def test_bootstrap_has_no_implicit_commissioning_profile_loader(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertNotIn("control-engine-tuning-validation-v1.json", text)
        self.assertNotIn("TuningValidationProfile", text)

    def test_readiness_contract_fails_closed_when_no_profile_is_bound(self) -> None:
        source = (
            ROOT / "src" / "ventilation_core" / "domain" / "actuation_readiness.py"
        ).read_text(encoding="utf-8")
        self.assertIn('blockers.append("TUNING_VALIDATION_PROFILE_NOT_BOUND")', source)
        self.assertIn('blockers.append("ACTUATION_AUTHORITY_NOT_IMPLEMENTED")', source)


if __name__ == "__main__":
    unittest.main()
