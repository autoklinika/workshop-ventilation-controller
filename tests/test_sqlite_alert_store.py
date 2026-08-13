import tempfile
import unittest
from pathlib import Path

from ventilation_core.application.alert_registry import AlertRegistry
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity
from ventilation_core.infrastructure.sqlite_alert_store import SqliteAlertStore


class SqliteAlertStoreTest(unittest.TestCase):
    def test_alert_ack_and_clear_survive_store_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "alerts.sqlite3"
            signal = AlertSignal(
                key="sensor-node:1:communication",
                code=AlarmCode.SENSOR_NODE_UNAVAILABLE,
                source="sensor:1",
                severity=AlarmSeverity.WARNING,
                message="Czujnik SEN55 1: brak poprawnej komunikacji",
                detail="timeout",
                occurrences=3,
            )
            registry = AlertRegistry(SqliteAlertStore(path))
            first = registry.reconcile([signal])[0]
            registry.acknowledge(first.alert_id)
            registry.close()

            registry = AlertRegistry(SqliteAlertStore(path))
            active = registry.active_records()
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0].alert_id, first.alert_id)
            self.assertTrue(active[0].acknowledged)
            registry.reconcile([])
            registry.close()

            registry = AlertRegistry(SqliteAlertStore(path))
            self.assertEqual(registry.active_records(), ())
            history = registry.history()
            self.assertEqual(history[0].alert_id, first.alert_id)
            self.assertTrue(history[0].acknowledged)
            self.assertIsNotNone(history[0].cleared_at)
            second = registry.reconcile([signal])[0]
            self.assertNotEqual(second.alert_id, first.alert_id)
            self.assertFalse(second.acknowledged)
            registry.close()

    def test_same_active_key_is_one_incident(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = AlertRegistry(SqliteAlertStore(Path(temp_dir) / "alerts.sqlite3"))
            signal = AlertSignal(
                key="aero-bus:communication",
                code=AlarmCode.AERO_BUS_UNAVAILABLE,
                source="aero_bus",
                severity=AlarmSeverity.WARNING,
                message="Rekuperator AERO: brak poprawnej komunikacji",
            )
            one = registry.reconcile([signal])[0]
            two = registry.reconcile([signal])[0]
            self.assertEqual(one.alert_id, two.alert_id)
            self.assertEqual(len(registry.active_records()), 1)
            registry.close()


if __name__ == "__main__":
    unittest.main()
