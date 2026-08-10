from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from ventilation_core.telemetry.store import TelemetryStore


class TelemetryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "telemetry.sqlite3"
        self.store = TelemetryStore(self.path)
        self.store.initialize()

    def test_reservation_is_stable_across_retries(self) -> None:
        self.store.append_snapshot({"mode": "STOP"}, sample_id="sample-1")
        self.store.append_snapshot({"mode": "STOP"}, sample_id="sample-2")
        first = self.store.reserve_batch(100)
        second = self.store.reserve_batch(100)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(first.created_at, second.created_at)
        self.assertEqual([sample.sample_id for sample in first.samples], ["sample-1", "sample-2"])

    def test_synced_rows_leave_pending_queue(self) -> None:
        self.store.append_snapshot({"mode": "STOP"})
        batch = self.store.reserve_batch(100)
        assert batch is not None
        self.assertEqual(self.store.pending_count(), 1)
        marked = self.store.mark_batch_synced(batch.batch_id)
        self.assertEqual(marked, 1)
        self.assertEqual(self.store.pending_count(), 0)
        self.assertEqual(self.store.total_count(), 1)

    def test_retention_never_deletes_pending_rows(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        self.store.append_snapshot({"mode": "STOP"}, captured_at=old, sample_id="pending")
        self.store.append_snapshot({"mode": "STOP"}, captured_at=old, sample_id="synced")
        batch = self.store.reserve_batch(1)
        assert batch is not None
        self.store.mark_batch_synced(batch.batch_id)
        deleted = self.store.prune_synced(30)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.store.total_count(), 1)
        self.assertEqual(self.store.pending_count(), 1)

    def test_sequence_is_monotonic(self) -> None:
        first = self.store.append_snapshot({"mode": "STOP"})
        second = self.store.append_snapshot({"mode": "STOP"})
        self.assertEqual(second.sequence, first.sequence + 1)


if __name__ == "__main__":
    unittest.main()
