import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ventilation_core.application.alert_registry import AlertRegistry
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity
from ventilation_core.infrastructure.sqlite_alert_store import (
    VOLATILE_FALLBACK_ENV,
    SqliteAlertStore,
)


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

    def test_exact_final_occurrences_are_persisted_on_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "alerts.sqlite3"
            signal = AlertSignal(
                key="aero-bus:communication",
                code=AlarmCode.AERO_BUS_UNAVAILABLE,
                source="aero_bus",
                severity=AlarmSeverity.WARNING,
                message="Rekuperator AERO: brak poprawnej komunikacji",
                detail="timeout",
                occurrences=3,
            )
            registry = AlertRegistry(
                SqliteAlertStore(path),
                occurrence_persist_step=30,
            )
            registry.reconcile([signal])
            for occurrences in range(4, 18):
                active = registry.reconcile(
                    [replace(signal, occurrences=occurrences)]
                )
                self.assertEqual(active[0].occurrences, occurrences)

            registry.reconcile([])
            registry.close()

            registry = AlertRegistry(SqliteAlertStore(path))
            history = registry.history()
            self.assertEqual(history[0].occurrences, 17)
            self.assertFalse(history[0].active)
            self.assertIsNotNone(history[0].cleared_at)
            registry.close()

    def test_unavailable_persistent_path_fails_without_explicit_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            blocker = Path(temp_dir) / "not-a-directory"
            blocker.write_text("block", encoding="utf-8")
            target = blocker / "alerts.sqlite3"
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(VOLATILE_FALLBACK_ENV, None)
                with self.assertRaises(OSError):
                    SqliteAlertStore(target)

    def test_explicit_volatile_fallback_keeps_alert_lifecycle_in_ram(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            blocker = Path(temp_dir) / "not-a-directory"
            blocker.write_text("block", encoding="utf-8")
            target = blocker / "alerts.sqlite3"
            signal = AlertSignal(
                key="system:undervoltage",
                code=AlarmCode.SYSTEM_UNDERVOLTAGE,
                source="system_power",
                severity=AlarmSeverity.CRITICAL,
                message="Undervoltage",
            )
            with patch.dict(os.environ, {VOLATILE_FALLBACK_ENV: "1"}):
                store = SqliteAlertStore(target)
                self.assertFalse(store.persistent)
                self.assertTrue(store.using_volatile_fallback)
                registry = AlertRegistry(store)
                record = registry.reconcile([signal])[0]
                self.assertTrue(record.active)
                registry.reconcile([])
                self.assertFalse(registry.history()[0].active)
                registry.close()
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
