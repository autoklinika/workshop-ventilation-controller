from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from ventilation_core.telemetry.history import (
    TelemetryHistoryReader,
    TelemetryHistoryUnavailable,
)
from ventilation_core.telemetry.store import TelemetryStore


class TelemetryHistoryReaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "telemetry.sqlite3"
        self.store = TelemetryStore(self.path)
        self.store.initialize()

    def test_status_reports_local_sync_rollup_and_size_counts(self) -> None:
        self.store.append_snapshot(
            {"mode": "STOP"},
            captured_at="2026-08-17T10:00:00+00:00",
            sample_id="sample-1",
        )
        self.store.append_snapshot(
            {"mode": "MANUAL"},
            captured_at="2026-08-17T10:00:05+00:00",
            sample_id="sample-2",
        )
        batch = self.store.reserve_batch(1)
        assert batch is not None
        self.store.mark_batch_synced(batch.batch_id)
        self.store.build_rollups(
            now=datetime(2026, 8, 17, 10, 16, tzinfo=timezone.utc),
            max_buckets_per_resolution=30,
        )

        status = TelemetryHistoryReader(self.path).status()
        self.assertTrue(status.available)
        self.assertEqual(status.total_samples, 2)
        self.assertEqual(status.synced_samples, 1)
        self.assertEqual(status.pending_samples, 1)
        self.assertEqual(status.oldest_captured_at, "2026-08-17T10:00:00+00:00")
        self.assertEqual(status.newest_captured_at, "2026-08-17T10:00:05+00:00")
        self.assertEqual(status.oldest_pending_at, "2026-08-17T10:00:05+00:00")
        self.assertIsNotNone(status.last_synced_at)
        self.assertEqual(status.rollup_1m_samples, 1)
        self.assertEqual(status.rollup_15m_samples, 1)
        self.assertGreater(status.database_bytes, 0)

    def test_query_is_bounded_and_returns_chronological_samples(self) -> None:
        for index in range(3):
            self.store.append_snapshot(
                {"mode": "STOP", "index": index},
                captured_at=f"2026-08-17T10:00:0{index}+00:00",
                sample_id=f"sample-{index}",
            )

        reader = TelemetryHistoryReader(self.path)
        samples = reader.query(
            start_at="2026-08-17T10:00:01+00:00",
            limit=2,
        )
        self.assertEqual([sample["metrics"]["index"] for sample in samples], [1, 2])
        self.assertTrue(all(sample["synced"] is False for sample in samples))
        self.assertTrue(all(sample["resolution"] == "raw" for sample in samples))

        with self.assertRaisesRegex(ValueError, "1..2000"):
            reader.query(limit=2001)

    def test_query_can_select_one_minute_and_fifteen_minute_rollups(self) -> None:
        self.store.append_snapshot(
            {"mode": "STOP", "setpoints": {"supply_voltage": 0.0}},
            captured_at="2026-08-17T10:00:05+00:00",
            sample_id="sample-1",
        )
        self.store.append_snapshot(
            {"mode": "MANUAL", "setpoints": {"supply_voltage": 4.0}},
            captured_at="2026-08-17T10:00:55+00:00",
            sample_id="sample-2",
        )
        self.store.build_rollups(
            now=datetime(2026, 8, 17, 10, 16, tzinfo=timezone.utc),
            max_buckets_per_resolution=30,
        )

        reader = TelemetryHistoryReader(self.path)
        minute = reader.query(resolution="1m", limit=10)
        quarter = reader.query(resolution="15m", limit=10)

        self.assertEqual(len(minute), 1)
        self.assertEqual(minute[0]["resolution"], "1m")
        self.assertEqual(minute[0]["sample_count"], 2)
        signal = minute[0]["rollup"]["signals"]["setpoints.supply_voltage"]
        self.assertEqual(signal["avg"], 2.0)
        self.assertEqual(signal["min"], 0.0)
        self.assertEqual(signal["max"], 4.0)

        self.assertEqual(len(quarter), 1)
        self.assertEqual(quarter[0]["resolution"], "15m")
        self.assertEqual(quarter[0]["sample_count"], 2)

        with self.assertRaisesRegex(ValueError, "raw, 1m, 15m"):
            reader.query(resolution="1h")

    def test_missing_database_is_reported_without_creating_it(self) -> None:
        missing = Path(self.tempdir.name) / "missing.sqlite3"
        reader = TelemetryHistoryReader(missing)
        self.assertFalse(reader.status().available)
        self.assertFalse(missing.exists())
        with self.assertRaises(TelemetryHistoryUnavailable):
            reader.query()
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
