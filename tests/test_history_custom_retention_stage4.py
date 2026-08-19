from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from ventilation_core.telemetry.long_range import LongRangeTelemetryStore
from ventilation_core.telemetry.long_range_history import (
    LongRangeTelemetryHistoryReader,
    STORAGE_CRITICAL_PERCENT,
    STORAGE_WARNING_PERCENT,
)
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


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class HistoryCustomRetentionStage4Test(unittest.TestCase):
    def test_local_cm5_retention_keeps_multi_year_layers(self) -> None:
        self.assertEqual(LongRangeTelemetryStore.QUARTER_RETENTION_DAYS, 1095)
        self.assertEqual(LongRangeTelemetryStore.HOURLY_RETENTION_DAYS, 1825)
        self.assertEqual(LongRangeTelemetryStore.DAILY_RETENTION_DAYS, 3650)

    def test_history_status_exposes_read_only_storage_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "telemetry.sqlite3"
            store = LongRangeTelemetryStore(path)
            store.initialize()
            status = LongRangeTelemetryHistoryReader(path).status().to_dict()

        storage = status["storage"]
        self.assertEqual(storage["warning_percent"], 70.0)
        self.assertEqual(storage["critical_percent"], 85.0)
        self.assertEqual(STORAGE_WARNING_PERCENT, 70.0)
        self.assertEqual(STORAGE_CRITICAL_PERCENT, 85.0)
        self.assertIn(storage["level"], {"ok", "warning", "critical"})
        self.assertGreater(storage["total_bytes"], 0)
        self.assertGreaterEqual(storage["free_bytes"], 0)

    def test_backend_supports_custom_one_year_and_five_year_ranges(self) -> None:
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

        one_year = service.query(
            {
                "start_at": "2025-08-19T20:00:00Z",
                "end_at": "2026-08-19T20:00:00Z",
                "resolution": "auto",
                "series": ["zone1.air.pm2_5"],
            }
        )
        self.assertEqual(one_year["resolution"], "1d")
        self.assertIsNone(one_year["range"]["preset"])

        five_years = service.query(
            {
                "start_at": "2021-08-20T20:00:00Z",
                "end_at": "2026-08-19T20:00:00Z",
                "resolution": "auto",
                "series": ["zone1.air.pm2_5"],
            }
        )
        self.assertEqual(five_years["resolution"], "1d")
        self.assertLessEqual(history.calls[-1]["limit"], 2500)

    def test_custom_range_ui_sends_explicit_dates_and_does_not_aggregate(self) -> None:
        js = (STATIC / "history-h4.js").read_text(encoding="utf-8")
        self.assertIn("HISTORY_H4_MAX_CUSTOM_DAYS = 1825", js)
        self.assertIn('request.start_at = historyClient.customStart', js)
        self.assertIn('request.end_at = historyClient.customEnd', js)
        self.assertIn('delete request.range', js)
        self.assertIn('"WŁASNY ZAKRES"', js)
        lowered = js.lower()
        self.assertNotIn("interpolate", lowered)
        self.assertNotIn("aggregate", lowered)
        self.assertNotIn("average", lowered)

    def test_storage_ui_renders_backend_owned_warning_and_critical_levels(self) -> None:
        js = (STATIC / "history-h4.js").read_text(encoding="utf-8")
        css = (STATIC / "history-h4.css").read_text(encoding="utf-8")
        self.assertIn('storage.level === "warning"', js)
        self.assertIn('storage.level === "critical"', js)
        self.assertIn("storage.warning_percent", js)
        self.assertIn("storage.critical_percent", js)
        self.assertIn(".v2-history-storage-alert.is-warning", css)
        self.assertIn(".v2-history-storage-alert.is-critical", css)

    def test_h4_assets_are_bundled_after_h3(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"history-h4.js"', server)
        self.assertIn('"history-h4.css"', server)
        self.assertIn("h4_js.read_bytes()", server)
        self.assertIn("h4_css.read_bytes()", server)
        self.assertLess(
            server.index('h3_js = (self.server.static_root / "history-h3.js")'),
            server.index('h4_js = (self.server.static_root / "history-h4.js")'),
        )

    def test_ai_telemetry_send_logic_is_byte_for_byte_unchanged_from_h3(self) -> None:
        agent = ROOT / "src" / "ventilation_core" / "telemetry" / "agent.py"
        client = ROOT / "src" / "ventilation_core" / "telemetry" / "http_client.py"
        self.assertEqual(
            git_blob_sha(agent),
            "54cfbcaa2fa1b5a3442cf7392e69097238d0a096",
        )
        self.assertEqual(
            git_blob_sha(client),
            "1f43c280117f9ecdff63e539e0d5fec380aee26b",
        )


if __name__ == "__main__":
    unittest.main()
