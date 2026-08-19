from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity
from ventilation_core.infrastructure.sqlite_alert_store import SqliteAlertStore


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def signal(key: str) -> AlertSignal:
    return AlertSignal(
        key=key,
        code=AlarmCode.SENSOR_NODE_UNAVAILABLE,
        source="sensor:1",
        severity=AlarmSeverity.WARNING,
        message=f"Test {key}",
        detail="stage42",
    )


class HistoryAlertFoldersStage42Test(unittest.TestCase):
    def test_alert_store_keeps_only_30_days_of_cleared_history(self) -> None:
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tempdir:
            store = SqliteAlertStore(Path(tempdir) / "alerts.sqlite3")

            old = store.create(
                signal("old-cleared"),
                active_since=(now - timedelta(days=40)).isoformat(),
            )
            store.clear(
                old.alert_id,
                (now - timedelta(days=31)).isoformat(),
            )

            recent = store.create(
                signal("recent-cleared"),
                active_since=(now - timedelta(days=20)).isoformat(),
            )
            store.clear(
                recent.alert_id,
                (now - timedelta(days=10)).isoformat(),
            )

            active = store.create(
                signal("old-active"),
                active_since=(now - timedelta(days=90)).isoformat(),
            )

            history = store.list_history(100)
            ids = {record.alert_id for record in history}
            self.assertNotIn(old.alert_id, ids)
            self.assertIn(recent.alert_id, ids)
            self.assertIn(active.alert_id, ids)
            self.assertEqual(store.list_active()[0].alert_id, active.alert_id)
            self.assertEqual(store.HISTORY_RETENTION_DAYS, 30)
            store.close()

    def test_explicit_prune_never_deletes_active_alerts(self) -> None:
        now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tempdir:
            store = SqliteAlertStore(Path(tempdir) / "alerts.sqlite3")
            active = store.create(
                signal("long-running-active"),
                active_since=(now - timedelta(days=120)).isoformat(),
            )
            deleted = store.prune_history(now=now)
            self.assertGreaterEqual(deleted, 0)
            self.assertEqual(store.list_active()[0].alert_id, active.alert_id)
            store.close()

    def test_history_alert_tile_replaces_chart_with_date_folders(self) -> None:
        js = (STATIC / "history-h42-alert-folders.js").read_text(encoding="utf-8")
        self.assertIn('button.textContent = "ALERTY"', js)
        self.assertIn('historyH42Mode = "alerts"', js)
        self.assertIn('historyH42SetChartControlsVisible(false)', js)
        self.assertIn('document.createElement("details")', js)
        self.assertIn('details.open = index === 0', js)
        self.assertIn("historyH42GroupByDate", js)
        self.assertIn("alert.cleared_at", js)
        self.assertNotIn("30 * 24 * 60", js)
        self.assertNotIn("Date.now() -", js)

    def test_alert_archive_groups_by_date_not_severity(self) -> None:
        js = (STATIC / "history-h42-alert-folders.js").read_text(encoding="utf-8")
        group_function = js[js.index("function historyH42GroupByDate"):js.index("function historyH42FolderSummary")]
        self.assertIn("historyH42DateKey(alert.cleared_at)", group_function)
        self.assertNotIn("severity", group_function.lower())

    def test_expanded_alert_folders_extend_page_instead_of_nested_scroll(self) -> None:
        css = (STATIC / "history-h42-alert-folders.css").read_text(encoding="utf-8")
        self.assertIn(".v2-history-alert-archive{height:auto", css)
        self.assertIn("grid-template-rows:auto auto", css)
        self.assertIn("overflow:visible", css)
        self.assertIn(".v2-history-alert-groups{min-height:0;overflow:visible", css)
        self.assertNotIn("height:calc(100vh - 230px)", css)
        self.assertNotIn("height:calc(100dvh - 230px)", css)
        self.assertNotIn("overflow-y:auto", css)
        self.assertNotIn("scrollbar-gutter:stable", css)

    def test_h42_assets_are_bundled_after_h41(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"history-h42-alert-folders.js"', server)
        self.assertIn('"history-h42-alert-folders.css"', server)
        self.assertIn("h42_alert_js.read_bytes()", server)
        self.assertIn("h42_alert_css.read_bytes()", server)
        self.assertLess(
            server.index('h41_alert_js = (self.server.static_root / "history-h41-alerts.js")'),
            server.index('h42_alert_js = (self.server.static_root / "history-h42-alert-folders.js")'),
        )
        self.assertLess(
            server.index('h41_alert_css = (self.server.static_root / "history-h41-alerts.css")'),
            server.index('h42_alert_css = (self.server.static_root / "history-h42-alert-folders.css")'),
        )

    def test_ai_telemetry_send_logic_remains_byte_for_byte_unchanged(self) -> None:
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "agent.py"),
            "54cfbcaa2fa1b5a3442cf7392e69097238d0a096",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "http_client.py"),
            "1f43c280117f9ecdff63e539e0d5fec380aee26b",
        )


if __name__ == "__main__":
    unittest.main()
