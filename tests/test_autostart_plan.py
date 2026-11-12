from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from ventilation_core.domain.autostart import (
    default_config, easter_sunday, polish_holidays, validate_config, year_days
)
from ventilation_core.infrastructure.sqlite_autostart_store import SqliteAutostartStore


class AutostartCalendarTests(unittest.TestCase):
    def test_default_sundays_and_polish_holidays_are_off(self) -> None:
        config = validate_config(default_config())
        days = {day["date"]: day for day in year_days(config, 2026)}
        self.assertEqual(len(days), 365)
        self.assertFalse(config["enabled"])
        self.assertFalse(config["schedule_enabled"])
        self.assertTrue(days["2026-01-02"]["enabled"])
        self.assertTrue(days["2026-01-03"]["enabled"])  # Saturday default on
        self.assertFalse(days["2026-01-04"]["enabled"])  # Sunday
        self.assertFalse(days["2026-01-06"]["enabled"])  # Epiphany
        self.assertFalse(days["2026-04-06"]["enabled"])  # Easter Monday
        self.assertFalse(days["2026-06-04"]["enabled"])  # Corpus Christi
        self.assertFalse(days["2026-12-24"]["enabled"])  # Christmas Eve since 2025
        self.assertFalse(days["2026-11-11"]["enabled"])
        self.assertEqual(days["2026-06-04"]["source"], "holiday")

    def test_easter_computus_and_leap_year(self) -> None:
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(easter_sunday(2027), date(2027, 3, 28))
        self.assertEqual(easter_sunday(2038), date(2038, 4, 25))
        self.assertEqual(len(year_days(default_config(), 2028)), 366)
        self.assertEqual(polish_holidays(2027)[date(2027, 5, 27)], "Boże Ciało")

    def test_manual_override_can_enable_holiday_and_disable_weekday(self) -> None:
        config = default_config()
        config["overrides"] = [
            {"date": "2026-01-06", "enabled": True},
            {"date": "2026-01-02", "enabled": False},
        ]
        days = {day["date"]: day for day in year_days(validate_config(config), 2026)}
        self.assertTrue(days["2026-01-06"]["enabled"])
        self.assertEqual(days["2026-01-06"]["source"], "override")
        self.assertFalse(days["2026-01-02"]["enabled"])

    def test_reject_incomplete_or_overnight_hours(self) -> None:
        config = default_config()
        config["week"][0]["start_local"] = "07:00"
        with self.assertRaises(ValueError):
            validate_config(config)
        config["week"][0]["end_local"] = "06:00"
        with self.assertRaises(ValueError):
            validate_config(config)
        config["week"][0]["end_local"] = "15:00"
        self.assertEqual(validate_config(config)["week"][0]["end_local"], "15:00")

    def test_reject_duplicates_and_invalid_dates(self) -> None:
        config = default_config()
        config["overrides"] = [{"date": "2026-02-30", "enabled": False}]
        with self.assertRaises(ValueError):
            validate_config(config)
        config["overrides"] = [
            {"date": "2026-02-20", "enabled": True},
            {"date": "2026-02-20", "enabled": False},
        ]
        with self.assertRaises(ValueError):
            validate_config(config)
        config = default_config()
        config["week"][1]["weekday"] = 1
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_persistence_is_versioned_and_non_actuating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "automation.sqlite3"
            store = SqliteAutostartStore(path)
            first = store.get(2026)
            self.assertFalse(first["actuation_enabled"])
            self.assertEqual(first["revision"], 1)
            config = first["config"]
            config["enabled"] = True
            config["schedule_enabled"] = True
            config["week"][0]["start_local"] = "08:00"
            config["week"][0]["end_local"] = "16:00"
            config["overrides"].append({"date": "2026-12-24", "enabled": True})
            saved = store.replace(config, 1, 2026)
            self.assertEqual(saved["revision"], 2)
            with self.assertRaises(ValueError):
                store.replace(config, 1, 2026)
            store.close()
            reopened = SqliteAutostartStore(path)
            self.assertEqual(reopened.get(2026)["revision"], 2)
            self.assertTrue(reopened.get(2026)["config"]["enabled"])
            self.assertFalse(reopened.get(2026)["actuation_enabled"])
            reopened.close()


class AutostartWebApiTests(unittest.TestCase):
    def test_web_reads_and_writes_via_core_only(self) -> None:
        from ventilation_core.web.app import WebApplication

        class FakeCore:
            def __init__(self):
                self.calls = []

            def request(self, command):
                self.calls.append(command)
                return {"ok": True, "autostart": {"available": True, "days": []}}

        fake = FakeCore()
        app = WebApplication(fake)
        self.assertEqual(app.handle("GET", "/api/v1/autostart/2026").status, 200)
        config = default_config()
        self.assertEqual(
            app.handle("POST", "/api/v1/autostart",
                       {"year": 2026, "expected_revision": 1, "config": config}).status,
            200,
        )
        self.assertEqual(fake.calls, [
            {"command": "autostart", "year": 2026},
            {"command": "autostart-replace", "year": 2026,
             "expected_revision": 1, "config": config},
        ])

    def test_web_rejects_bad_revision_and_commands(self) -> None:
        from ventilation_core.web.app import WebApplication

        class NoCore:
            def request(self, _):
                raise AssertionError("invalid inputs must never reach core")

        app = WebApplication(NoCore())
        self.assertEqual(app.handle("GET", "/api/v1/autostart/2026x").status, 400)
        self.assertEqual(app.handle("POST", "/api/v1/autostart",
                                    {"year": 2026, "expected_revision": True,
                                     "config": default_config()}).status, 400)
        self.assertEqual(app.handle("POST", "/api/v1/autostart",
                                    {"year": 2026, "expected_revision": 1,
                                     "config": default_config(), "command": "stop"}).status, 400)


class AutostartUiContractTests(unittest.TestCase):
    def test_ui_assets_and_nonactuating_contract(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src/ventilation_core/web"
        html = (root / "static/settings.html").read_text()
        js = (root / "static/autostart.js").read_text()
        server = (root / "server.py").read_text()
        self.assertIn('data-settings-panel="autostart"', html)
        self.assertIn('id="autostartMonths"', html)
        self.assertIn('id="autostartWeek"', html)
        self.assertIn('id="autostartEnabled"', html)
        self.assertIn('id="autostartScheduleEnabled"', html)
        self.assertIn("/api/v1/autostart", js)
        self.assertIn("autostart.css", server)
        self.assertIn("autostart.js", server)
        self.assertIn("BEZ AKTUACJI", html)


if __name__ == "__main__":
    unittest.main()
