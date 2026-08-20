from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest

from ventilation_core.web.alert_history import SqliteAlertHistoryReader
from ventilation_core.web.alert_history_app import AlertHistoryWebApplication


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def create_alert_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL,
            code TEXT NOT NULL,
            source TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            active_since TEXT NOT NULL,
            acknowledged_at TEXT,
            cleared_at TEXT,
            occurrences INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    return db


def insert_alert(
    db: sqlite3.Connection,
    *,
    key: str,
    severity: str,
    cleared_at: str | None,
    occurrences: int = 1,
) -> int:
    cursor = db.execute(
        """
        INSERT INTO alerts (
            alert_key, code, source, severity, message, detail,
            active_since, acknowledged_at, cleared_at, occurrences
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            key,
            "SENSOR_NODE_UNAVAILABLE",
            "sensor:1",
            severity,
            f"Alert {key}",
            "stage43",
            "2026-08-18T20:00:00+00:00",
            cleared_at,
            occurrences,
        ),
    )
    return int(cursor.lastrowid)


class FakeCore:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        self.requests.append(payload)
        return {"ok": True, "state": {"mode": "STOP"}}


class FakeAlertHistory:
    DEFAULT_INDEX_WINDOW_DAYS = 90
    DEFAULT_DAY_PAGE_SIZE = 100

    def __init__(self) -> None:
        self.days_calls: list[dict[str, object]] = []
        self.day_calls: list[dict[str, object]] = []

    def day_index(self, **kwargs: object) -> dict[str, object]:
        self.days_calls.append(dict(kwargs))
        return {
            "timezone": kwargs["timezone_name"],
            "days": [{"day": "2026-08-19", "count": 42, "critical": 0, "warning": 42, "other": 0}],
            "has_older": False,
            "next_before_day": None,
            "total_closed": 100,
        }

    def query_day(self, **kwargs: object) -> dict[str, object]:
        self.day_calls.append(dict(kwargs))
        return {
            "timezone": kwargs["timezone_name"],
            "day": kwargs["day"],
            "records": [],
            "returned": 0,
            "total_for_day": 0,
            "has_more": False,
            "next_cursor": None,
        }


class HistoryAlertPaginationStage43Test(unittest.TestCase):
    def test_index_uses_browser_timezone_for_calendar_day(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "alerts.sqlite3"
            db = create_alert_db(path)
            insert_alert(
                db,
                key="local-19",
                severity="warning",
                cleared_at="2026-08-18T22:30:00+00:00",
            )
            insert_alert(
                db,
                key="local-18",
                severity="critical",
                cleared_at="2026-08-18T21:30:00+00:00",
            )
            insert_alert(
                db,
                key="still-active",
                severity="warning",
                cleared_at=None,
            )
            db.commit()
            db.close()

            reader = SqliteAlertHistoryReader(path)
            index = reader.day_index(
                timezone_name="Europe/Warsaw",
                before_day="2026-08-20",
                window_days=3,
            )

            self.assertEqual(index["total_closed"], 2)
            by_day = {item["day"]: item for item in index["days"]}
            self.assertEqual(by_day["2026-08-19"]["warning"], 1)
            self.assertEqual(by_day["2026-08-18"]["critical"], 1)
            self.assertNotIn("2026-08-20", by_day)

    def test_day_records_are_cursor_paginated_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "alerts.sqlite3"
            db = create_alert_db(path)
            expected: set[int] = set()
            for minute in (55, 50, 45, 40, 35):
                expected.add(
                    insert_alert(
                        db,
                        key=f"a-{minute}",
                        severity="warning",
                        cleared_at=f"2026-08-19T19:{minute:02d}:00+00:00",
                    )
                )
            db.commit()
            db.close()

            reader = SqliteAlertHistoryReader(path)
            first = reader.query_day(
                day="2026-08-19",
                timezone_name="Europe/Warsaw",
                limit=2,
            )
            self.assertEqual(len(first["records"]), 2)
            self.assertTrue(first["has_more"])
            self.assertIsNotNone(first["next_cursor"])

            second = reader.query_day(
                day="2026-08-19",
                timezone_name="Europe/Warsaw",
                limit=2,
                **first["next_cursor"],
            )
            self.assertEqual(len(second["records"]), 2)
            self.assertTrue(second["has_more"])

            third = reader.query_day(
                day="2026-08-19",
                timezone_name="Europe/Warsaw",
                limit=2,
                **second["next_cursor"],
            )
            self.assertEqual(len(third["records"]), 1)
            self.assertFalse(third["has_more"])

            seen = {
                record["alert_id"]
                for page in (first, second, third)
                for record in page["records"]
            }
            self.assertEqual(seen, expected)

    def test_index_window_exposes_older_history_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "alerts.sqlite3"
            db = create_alert_db(path)
            insert_alert(
                db,
                key="recent",
                severity="warning",
                cleared_at="2026-08-19T10:00:00+00:00",
            )
            insert_alert(
                db,
                key="old",
                severity="warning",
                cleared_at="2026-01-10T10:00:00+00:00",
            )
            db.commit()
            db.close()

            reader = SqliteAlertHistoryReader(path)
            index = reader.day_index(
                timezone_name="Europe/Warsaw",
                before_day="2026-08-21",
                window_days=90,
            )
            self.assertTrue(index["has_older"])
            self.assertEqual(index["next_before_day"], "2026-05-23")
            self.assertEqual(index["total_closed"], 2)

    def test_webui_paged_alert_history_does_not_call_core(self) -> None:
        core = FakeCore()
        provider = FakeAlertHistory()
        app = AlertHistoryWebApplication(core, alert_history=provider)

        days = app.handle(
            "POST",
            "/api/v1/history/alerts/days",
            {"timezone": "Europe/Warsaw", "window_days": 90},
        )
        self.assertEqual(days.status, 200)
        self.assertEqual(days.payload["alert_history"]["total_closed"], 100)

        day = app.handle(
            "POST",
            "/api/v1/history/alerts/day",
            {
                "timezone": "Europe/Warsaw",
                "day": "2026-08-19",
                "limit": 100,
                "cursor": {
                    "before_cleared_at": "2026-08-19T10:00:00+00:00",
                    "before_alert_id": 50,
                },
            },
        )
        self.assertEqual(day.status, 200)
        self.assertEqual(core.requests, [])
        self.assertEqual(provider.day_calls[0]["before_alert_id"], 50)

    def test_gui_loads_date_index_then_day_on_demand(self) -> None:
        js = (STATIC / "history-h43-alert-pagination.js").read_text(encoding="utf-8")
        self.assertIn('"/api/v1/history/alerts/days"', js)
        self.assertIn('"/api/v1/history/alerts/day"', js)
        self.assertIn("HISTORY_H43_INDEX_WINDOW_DAYS = 90", js)
        self.assertIn("HISTORY_H43_DAY_PAGE_SIZE = 100", js)
        self.assertIn('details.addEventListener("toggle"', js)
        self.assertIn("if (details.open) historyH43LoadDay(summary.day)", js)
        self.assertIn("POKAŻ KOLEJNE WPISY", js)
        self.assertIn("POKAŻ STARSZE DNI", js)
        self.assertIn("next_cursor", js)
        self.assertNotIn('fetch("/api/v1/alerts"', js)
        self.assertNotIn("DELETE FROM alerts", js)

    def test_gui_preserves_open_folders_during_index_refresh(self) -> None:
        js = (STATIC / "history-h43-alert-pagination.js").read_text(encoding="utf-8")
        self.assertIn("historyH42OpenFolderKeys.has(summary.day)", js)
        self.assertIn("historyH42RememberFolderState(details)", js)
        self.assertIn("historyH43IndexSignature", js)
        self.assertIn("signature === historyH43State.indexSignature", js)
        self.assertIn("historyH42CaptureFolderState(host)", js)

    def test_stage43_is_webui_read_only_and_does_not_change_core_protocol(self) -> None:
        # H4.3 owns a WebUI-side read-only history path. Guard the actual
        # core socket protocol plus authoritative alert lifecycle/persistence
        # boundaries. Alert detector implementations may legitimately evolve
        # independently (for example, adding SYSTEM_UNDERVOLTAGE) without
        # changing the H4.3 protocol invariant.
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "runtime" / "server.py"),
            "bb906449e7aa4582c97d9db60655dd3a9fc101ce",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "application" / "alert_registry.py"),
            "097dbd9ad975e6f6c1a8239f56495cf1284bdd41",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "infrastructure" / "sqlite_alert_store.py"),
            "8a232fe46142186e9564ba53c8b43f5ca6bf14a1",
        )

    def test_ai_telemetry_send_logic_is_still_byte_for_byte_unchanged(self) -> None:
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "agent.py"),
            "54cfbcaa2fa1b5a3442cf7392e69097238d0a096",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "http_client.py"),
            "1f43c280117f9ecdff63e539e0d5fec380aee26b",
        )

    def test_stage43_assets_are_bundled_after_stage42(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"history-h43-alert-pagination.js"', server)
        self.assertIn('"history-h43-alert-pagination.css"', server)
        self.assertIn("h43_alert_js.read_bytes()", server)
        self.assertIn("h43_alert_css.read_bytes()", server)
        self.assertLess(
            server.index('h42_alert_js = (self.server.static_root / "history-h42-alert-folders.js")'),
            server.index('h43_alert_js = (self.server.static_root / "history-h43-alert-pagination.js")'),
        )
        self.assertLess(
            server.index('h42_alert_css = (self.server.static_root / "history-h42-alert-folders.css")'),
            server.index('h43_alert_css = (self.server.static_root / "history-h43-alert-pagination.css")'),
        )

    def test_web_main_wires_read_only_alert_database(self) -> None:
        main = (ROOT / "src" / "ventilation_core" / "web" / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("DEFAULT_ALERT_DATABASE", main)
        self.assertIn("WVC_WEB_ALERT_DATABASE", main)
        self.assertIn("SqliteAlertHistoryReader", main)
        self.assertIn("AlertHistoryWebApplication", main)
        self.assertIn("alert_history=alert_history", main)


if __name__ == "__main__":
    unittest.main()
