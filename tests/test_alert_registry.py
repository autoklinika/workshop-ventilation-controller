import unittest
from dataclasses import replace

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity


class CountingMemoryAlertStore(MemoryAlertStore):
    def __init__(self) -> None:
        super().__init__()
        self.update_calls = 0

    def update_active(self, record, signal):
        self.update_calls += 1
        return super().update_active(record, signal)


class AlertRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AlertRegistry(MemoryAlertStore())
        self.signal = AlertSignal(
            key="aero-bus:communication",
            code=AlarmCode.AERO_BUS_UNAVAILABLE,
            source="aero_bus",
            severity=AlarmSeverity.WARNING,
            message="Rekuperator AERO: brak poprawnej komunikacji",
            detail="timeout",
            occurrences=3,
        )

    def test_acknowledgement_does_not_clear_active_alert(self) -> None:
        active = self.registry.reconcile([self.signal])
        self.assertEqual(len(active), 1)
        alert_id = active[0].alert_id
        self.registry.acknowledge(alert_id)
        active = self.registry.reconcile([self.signal])
        self.assertEqual(active[0].alert_id, alert_id)
        self.assertTrue(active[0].active)
        self.assertTrue(active[0].acknowledged)

    def test_clear_then_reoccurrence_creates_new_incident(self) -> None:
        first = self.registry.reconcile([self.signal])[0]
        self.registry.acknowledge(first.alert_id)
        self.assertEqual(self.registry.reconcile([]), ())
        history = self.registry.history()
        self.assertIsNotNone(history[0].cleared_at)
        self.assertTrue(history[0].acknowledged)
        second = self.registry.reconcile([self.signal])[0]
        self.assertNotEqual(second.alert_id, first.alert_id)
        self.assertFalse(second.acknowledged)

    def test_material_update_preserves_incident_and_ack(self) -> None:
        first = self.registry.reconcile([self.signal])[0]
        self.registry.acknowledge(first.alert_id)
        changed = AlertSignal(
            key=self.signal.key,
            code=self.signal.code,
            source=self.signal.source,
            severity=self.signal.severity,
            message=self.signal.message,
            detail="CRC error",
            occurrences=5,
        )
        updated = self.registry.reconcile([changed])[0]
        self.assertEqual(updated.alert_id, first.alert_id)
        self.assertTrue(updated.acknowledged)
        self.assertEqual(updated.detail, "CRC error")
        self.assertEqual(updated.occurrences, 5)

    def test_occurrence_growth_is_batched_but_visible_and_exact_on_clear(self) -> None:
        store = CountingMemoryAlertStore()
        registry = AlertRegistry(store, occurrence_persist_step=30)
        first = registry.reconcile([self.signal])[0]
        self.assertEqual(first.occurrences, 3)

        for occurrences in range(4, 33):
            active = registry.reconcile(
                [replace(self.signal, occurrences=occurrences)]
            )
            self.assertEqual(active[0].occurrences, occurrences)

        self.assertEqual(store.update_calls, 0)
        self.assertEqual(store.list_active()[0].occurrences, 3)

        active = registry.reconcile([replace(self.signal, occurrences=33)])
        self.assertEqual(active[0].occurrences, 33)
        self.assertEqual(store.update_calls, 1)
        self.assertEqual(store.list_active()[0].occurrences, 33)

        for occurrences in range(34, 42):
            active = registry.reconcile(
                [replace(self.signal, occurrences=occurrences)]
            )
            self.assertEqual(active[0].occurrences, occurrences)

        self.assertEqual(store.update_calls, 1)
        self.assertEqual(registry.reconcile([]), ())
        history = registry.history()
        self.assertEqual(history[0].occurrences, 41)
        self.assertIsNotNone(history[0].cleared_at)

        second = registry.reconcile([replace(self.signal, occurrences=100)])[0]
        self.assertNotEqual(second.alert_id, first.alert_id)
        old = next(record for record in registry.history() if record.alert_id == first.alert_id)
        self.assertEqual(old.occurrences, 41)

    def test_invalid_acknowledgement_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.acknowledge(0)
        with self.assertRaises(ValueError):
            self.registry.acknowledge(True)
        with self.assertRaises(ValueError):
            self.registry.acknowledge(999)


if __name__ == "__main__":
    unittest.main()
