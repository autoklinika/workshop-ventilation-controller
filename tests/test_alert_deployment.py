import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ventilation_core.main import build_parser, run_core


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy" / "systemd" / "ventilation-core.service"


class AlertDeploymentTest(unittest.TestCase):
    def test_core_parser_keeps_legacy_default_for_non_production_invocation(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(
            args.alerts_db,
            Path("/var/lib/workshop-ventilation/alerts.sqlite3"),
        )

    def test_production_unit_routes_alert_history_to_nvme_with_ram_fallback(self) -> None:
        unit = UNIT.read_text(encoding="utf-8")
        self.assertIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn("StateDirectoryMode=0770", unit)
        self.assertIn(
            "--alerts-db /srv/wvc-data/workshop-ventilation/alerts.sqlite3",
            unit,
        )
        self.assertIn("WVC_ALERT_STORE_ALLOW_VOLATILE_FALLBACK=1", unit)
        self.assertIn(
            "--automation-db /var/lib/workshop-ventilation/automation.sqlite3",
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
