import unittest
from pathlib import Path

from ventilation_core.main import build_parser


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy" / "systemd" / "ventilation-core.service"


class AlertDeploymentTest(unittest.TestCase):
    def test_core_owns_persistent_alert_database_path(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(
            args.alerts_db,
            Path("/var/lib/workshop-ventilation/alerts.sqlite3"),
        )

    def test_systemd_provisions_core_state_directory_and_database(self) -> None:
        unit = UNIT.read_text(encoding="utf-8")
        self.assertIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn("StateDirectoryMode=0770", unit)
        self.assertIn(
            "--alerts-db /var/lib/workshop-ventilation/alerts.sqlite3",
            unit,
        )
        self.assertIn("User=wentylacja", unit)
        self.assertIn("Group=wentylacja", unit)


if __name__ == "__main__":
    unittest.main()
