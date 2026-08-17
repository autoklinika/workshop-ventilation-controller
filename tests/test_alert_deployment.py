import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ventilation_core.main import build_parser, run_core


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


class AlertStartupCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_registry_closes_if_actuator_constructor_fails(self) -> None:
        args = build_parser().parse_args(
            ["--disable-sensor-bus", "--disable-aero-bus"]
        )
        store = Mock()
        registry = Mock()

        with (
            patch(
                "ventilation_core.main.SqliteAlertStore",
                return_value=store,
            ),
            patch(
                "ventilation_core.main.AlertRegistry",
                return_value=registry,
            ),
            patch(
                "ventilation_core.main.ProcessIsolatedActuator",
                side_effect=RuntimeError("DAC init failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "DAC init failed"):
                await run_core(args)

        registry.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
