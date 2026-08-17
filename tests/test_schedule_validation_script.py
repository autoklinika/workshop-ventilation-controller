from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class ScheduleValidationScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(__file__).resolve().parents[1] / "tools" / "validate_schedule_stage1_cm5.sh"
        self.text = self.path.read_text(encoding="utf-8")

    def test_bash_syntax_is_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(self.path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validation_uses_isolated_schedule_databases_and_restores_production(self) -> None:
        self.assertIn('TEST_AUTOMATION_DB="/tmp/wvc-schedule-stage1-automation.sqlite3"', self.text)
        self.assertIn('TEST_ALERTS_DB="/tmp/wvc-schedule-stage1-alerts.sqlite3"', self.text)
        self.assertNotIn('/var/lib/workshop-ventilation/automation.sqlite3', self.text)
        self.assertIn('trap cleanup EXIT', self.text)
        self.assertIn('sudo systemctl stop "$CORE_SERVICE"', self.text)
        self.assertIn('sudo systemctl start "$CORE_SERVICE"', self.text)
        self.assertIn('prod_ctl stop', self.text)

    def test_validation_pauses_production_clients_while_test_core_owns_hardware(self) -> None:
        self.assertIn('sudo systemctl stop "$TELEMETRY_SERVICE"', self.text)
        self.assertIn('sudo systemctl stop "$WEB_SERVICE"', self.text)
        self.assertIn('sudo systemctl start "$TELEMETRY_SERVICE"', self.text)
        self.assertIn('sudo systemctl start "$WEB_SERVICE"', self.text)

    def test_validation_exercises_gui_api_persistence_and_negative_boundary(self) -> None:
        self.assertIn('/api/v1/schedule/zone', self.text)
        self.assertIn('schedule survived core restart: PASS', self.text)
        self.assertIn('arbitrary command rejected before core actuation: PASS', self.text)
        self.assertIn('SCHEDULE STAGE 1 — CM5 E2E VALIDATION: PASS', self.text)


if __name__ == "__main__":
    unittest.main()
