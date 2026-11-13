"""Contract for the recorded 2026-11-13 CM5 Autostart production snapshot.

The snapshot is evidence only: tests never write to the live CM5 database,
enable systemd timers, or issue RTC/host-power commands.
"""
from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

from ventilation_core.domain.autostart import validate_config, year_days

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "config/autostart-production-20261113.snapshot.json"
GATE = ROOT / "deploy/cm5/wvc-autostart-power-gate.py"
spec = importlib.util.spec_from_file_location("wvc_snapshotted_power_gate", GATE)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class ProductionAutostartSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.config = validate_config(cls.snapshot["config"])

    def test_documented_revision_is_a_nonexecuting_snapshot(self):
        self.assertEqual(self.snapshot["snapshot_schema_version"], 1)
        self.assertEqual(self.snapshot["source_revision"], 4)
        self.assertEqual(self.snapshot["year"], 2026)
        self.assertEqual(self.snapshot["config"], self.config)
        self.assertTrue(self.config["enabled"])
        self.assertTrue(self.config["schedule_enabled"])
        self.assertEqual(self.config["overrides"], [])
        self.assertEqual(
            [day["enabled"] for day in self.config["week"]],
            [True, True, True, True, True, False, False],
        )
        for day in self.config["week"][:6]:
            self.assertEqual(day["start_local"], "08:00")
            self.assertEqual(day["end_local"], "18:30")

    def test_saturday_sunday_off_monday_on(self):
        by_date = {day["date"]: day for day in year_days(self.config, 2026)}
        for date, enabled in [
            ("2026-11-13", True),
            ("2026-11-14", False),
            ("2026-11-15", False),
            ("2026-11-16", True),
            ("2026-12-24", False),
            ("2026-12-25", False),
        ]:
            with self.subTest(date=date):
                self.assertIs(by_date[date]["enabled"], enabled)

    def test_next_wake_respects_live_weekdays_and_holidays(self):
        def snapshot_loader(year):
            return {
                "year": year,
                "revision": self.snapshot["source_revision"],
                "config": self.config,
                "days": year_days(self.config, year),
            }

        cases = [
            ("2026-11-13T18:30:00", True, "2026-11-16T08:00:00+01:00"),
            ("2026-11-14T18:30:00", False, None),
            ("2026-12-23T18:30:00", True, "2026-12-28T08:00:00+01:00"),
            ("2026-12-31T18:30:00", True, "2027-01-04T08:00:00+01:00"),
        ]
        for when, due, wake in cases:
            with self.subTest(when=when):
                now = datetime.fromisoformat(when).replace(tzinfo=ZoneInfo("Europe/Warsaw"))
                plan = gate.build_plan(now, snapshot_loader)
                self.assertIs(plan.due_now, due)
                self.assertEqual(plan.next_wake_local, wake)


if __name__ == "__main__":
    unittest.main()
