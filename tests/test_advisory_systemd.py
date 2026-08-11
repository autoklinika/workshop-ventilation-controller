import unittest
from pathlib import Path


UNIT_PATH = Path(__file__).resolve().parents[1] / "deploy" / "systemd" / "wvc-ai-advisory.service"


class AdvisorySystemdUnitTest(unittest.TestCase):
    def test_advisory_service_has_no_control_service_dependency(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Requires=ventilation-core.service", unit)
        self.assertNotIn("After=ventilation-core.service", unit)

    def test_advisory_service_runs_as_ventilation_user(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("User=wentylacja", unit)
        self.assertIn("Group=wentylacja", unit)

    def test_advisory_service_writes_only_separate_cache(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn("/var/lib/workshop-ventilation/ai-advisory.json", unit)
        self.assertNotIn("ventilation-core.sock", unit)
        self.assertNotIn("telemetry.sqlite3", unit)


if __name__ == "__main__":
    unittest.main()
