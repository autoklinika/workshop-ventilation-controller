from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ventilation_core.telemetry.long_range import LongRangeTelemetryStore
from ventilation_core.telemetry.long_range_history import LongRangeTelemetryHistoryReader
from ventilation_core.web.config import WebUiConfig
from ventilation_core.web.history_series import HistorySeriesService


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class FakeHistory:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query(self, **kwargs):
        self.calls.append(dict(kwargs))
        return []


class HistoryLongRangeStage3Test(unittest.TestCase):
    def test_store_creates_and_builds_hourly_and_daily_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "telemetry.sqlite3"
            store = LongRangeTelemetryStore(path)
            store.initialize()
            store.append_snapshot(
                {"setpoints": {"supply_voltage": 4.0}},
                captured_at="2026-08-17T10:05:00+00:00",
                sample_id="stage3-sample",
            )
            built = store.build_rollups(
                now=datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc),
                max_buckets_per_resolution=240,
            )
            self.assertEqual(built["1h"], 1)
            self.assertEqual(built["1d"], 1)
            self.assertEqual(store.rollup_count("1h"), 1)
            self.assertEqual(store.rollup_count("1d"), 1)

    def test_long_range_reader_returns_hourly_and_daily_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "telemetry.sqlite3"
            store = LongRangeTelemetryStore(path)
            store.initialize()
            store.append_snapshot(
                {"setpoints": {"supply_voltage": 4.0}},
                captured_at="2026-08-17T10:05:00+00:00",
                sample_id="reader-sample",
            )
            store.build_rollups(
                now=datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc),
                max_buckets_per_resolution=240,
            )
            reader = LongRangeTelemetryHistoryReader(path)
            hourly = reader.query(resolution="1h", limit=10)
            daily = reader.query(resolution="1d", limit=10)
            self.assertEqual(hourly[0]["resolution"], "1h")
            self.assertEqual(daily[0]["resolution"], "1d")
            self.assertEqual(hourly[0]["sample_count"], 1)
            self.assertEqual(daily[0]["sample_count"], 1)

    def test_raw_prune_waits_for_all_four_rollup_states(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "telemetry.sqlite3"
            store = LongRangeTelemetryStore(path)
            store.initialize()
            old = "2026-08-01T10:00:05+00:00"
            store.append_snapshot({"mode": "STOP"}, captured_at=old, sample_id="old")
            batch = store.reserve_batch(1)
            assert batch is not None
            store.mark_batch_synced(batch.batch_id)
            now = datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc)

            with closing(sqlite3.connect(path)) as connection:
                for resolution in ("1m", "15m", "1h"):
                    connection.execute(
                        "INSERT INTO telemetry_rollup_state(resolution, processed_until) VALUES (?, ?)",
                        (resolution, now.isoformat()),
                    )
                connection.commit()

            deleted = store.prune_history(
                raw_retention_days=7,
                minute_retention_days=90,
                quarter_retention_days=730,
                now=now,
            )
            self.assertEqual(deleted["raw"], 0)
            self.assertEqual(store.total_count(), 1)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "INSERT INTO telemetry_rollup_state(resolution, processed_until) VALUES (?, ?)",
                    ("1d", now.isoformat()),
                )
                connection.commit()

            deleted = store.prune_history(
                raw_retention_days=7,
                minute_retention_days=90,
                quarter_retention_days=730,
                now=now,
            )
            self.assertEqual(deleted["raw"], 1)

    def test_series_catalog_and_auto_resolution_cover_long_ranges(self) -> None:
        history = FakeHistory()
        config = WebUiConfig(
            zone1_name="Mycie",
            zone1_sensor_address=1,
            zone2_name="Lutowanie",
            zone2_sensor_address=2,
        )
        service = HistorySeriesService(
            history,
            config,
            now=lambda: datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc),
        )
        catalog = service.catalog()
        self.assertEqual(
            [item["id"] for item in catalog["ranges"]],
            ["1h", "24h", "7d", "30d", "90d", "1y"],
        )
        expected = {"30d": "1h", "90d": "1h", "1y": "1d"}
        for range_id, resolution in expected.items():
            payload = service.query({"range": range_id, "series": ["zone1.air.pm2_5"]})
            self.assertEqual(payload["resolution"], resolution)
        self.assertLessEqual(history.calls[1]["limit"], 2500)

    def test_web_and_telemetry_entrypoints_use_long_range_components(self) -> None:
        web_main = (ROOT / "src" / "ventilation_core" / "web" / "main.py").read_text(encoding="utf-8")
        telemetry_main = (ROOT / "src" / "ventilation_core" / "telemetry" / "main.py").read_text(encoding="utf-8")
        self.assertIn("LongRangeTelemetryHistoryReader", web_main)
        self.assertIn("LongRangeTelemetryStore", telemetry_main)

    def test_history_ui_exposes_long_range_labels_without_client_aggregation(self) -> None:
        js = (STATIC / "history-h3.js").read_text(encoding="utf-8")
        self.assertIn('"30d": "30 DNI"', js)
        self.assertIn('"90d": "90 DNI"', js)
        self.assertIn('"1y": "1 ROK"', js)
        self.assertIn('"1h": "1 GODZ."', js)
        self.assertIn('"1d": "1 DZIEŃ"', js)
        lowered = js.lower()
        for forbidden in ("fetch(", "historypost(", "/api/", "aggregate", "interpolate"):
            self.assertNotIn(forbidden, lowered)

    def test_long_range_ui_asset_is_bundled_after_h23(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn('"history-h3.js"', server)
        self.assertIn("h3_js.read_bytes()", server)
        self.assertLess(
            server.index('h23_js = (self.server.static_root / "history-h23.js")'),
            server.index('h3_js = (self.server.static_root / "history-h3.js")'),
        )


if __name__ == "__main__":
    unittest.main()
