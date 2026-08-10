import unittest
from pathlib import Path


UNIT_PATH = Path(__file__).resolve().parents[1] / "deploy" / "systemd" / "wvc-telemetry-sync.service"


class TelemetrySystemdUnitTest(unittest.TestCase):
    def test_telemetry_service_does_not_require_core(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("After=ventilation-core.service", unit)
        self.assertNotIn("Requires=ventilation-core.service", unit)

    def test_telemetry_service_runs_as_ventilation_user(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("User=wentylacja", unit)
        self.assertIn("Group=wentylacja", unit)

    def test_telemetry_service_has_separate_state_directory(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn("/var/lib/workshop-ventilation/telemetry.sqlite3", unit)


if __name__ == "__main__":
    unittest.main()
