"""Non-actuating tests for the WVC host-power Autostart gate."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

from ventilation_core.domain.autostart import default_config, validate_config, year_days

PATH = Path(__file__).resolve().parents[1] / "deploy/cm5/wvc-autostart-power-gate.py"
SPEC = importlib.util.spec_from_file_location("wvc_autostart_power_gate", PATH)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

ZONE = ZoneInfo("Europe/Warsaw")


def at(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=ZONE)


def configuration() -> dict:
    data = default_config()
    data["enabled"] = True
    data["schedule_enabled"] = True
    for row in data["week"][:6]:
        row["start_local"] = "08:00"
        row["end_local"] = "18:30"
    return validate_config(data)


def loader_for(data):
    def load(year):
        return {
            "revision": 3,
            "config": data,
            "days": year_days(data, year),
        }
    return load


class AutostartPowerGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = configuration()
        self.loader = loader_for(self.data)

    def test_friday_close_arms_saturday_start(self):
        plan = gate.build_plan(at(2026, 11, 13, 18, 30), self.loader)
        self.assertTrue(plan.due_now)
        self.assertEqual(plan.next_wake_local, "2026-11-14T08:00:00+01:00")

    def test_friday_outside_close_does_not_shutdown(self):
        for candidate in (at(2026, 11, 13, 8, 0), at(2026, 11, 13, 18, 29),
                          at(2026, 11, 13, 18, 31), at(2026, 11, 13, 19, 0)):
            with self.subTest(candidate=candidate):
                plan = gate.build_plan(candidate, self.loader)
                self.assertFalse(plan.due_now)
                self.assertEqual(plan.reason, "outside_close_minute")

    def test_saturday_shutdown_skips_sunday(self):
        plan = gate.build_plan(at(2026, 11, 14, 18, 30), self.loader)
        self.assertTrue(plan.due_now)
        self.assertEqual(plan.next_wake_local, "2026-11-16T08:00:00+01:00")

    def test_holiday_shutdown_skips_christmas_and_sunday(self):
        plan = gate.build_plan(at(2026, 12, 23, 18, 30), self.loader)
        self.assertTrue(plan.due_now)
        self.assertEqual(plan.next_wake_local, "2026-12-28T08:00:00+01:00")

    def test_new_year_skips_january_first(self):
        plan = gate.build_plan(at(2026, 12, 31, 18, 30), self.loader)
        self.assertTrue(plan.due_now)
        self.assertEqual(plan.next_wake_local, "2027-01-02T08:00:00+01:00")

    def test_holiday_is_not_shutdown_day(self):
        plan = gate.build_plan(at(2026, 12, 24, 18, 30), self.loader)
        self.assertFalse(plan.due_now)
        self.assertEqual(plan.reason, "non_working_day")

    def test_override_can_reactivate_holiday(self):
        self.data["overrides"] = [{"date": "2026-12-24", "enabled": True}]
        source = loader_for(validate_config(self.data))
        plan = gate.build_plan(at(2026, 12, 23, 18, 30), source)
        self.assertTrue(plan.due_now)
        self.assertEqual(plan.next_wake_local, "2026-12-24T08:00:00+01:00")

    def test_two_global_switches_block_actions_independently(self):
        for key, expected in [("enabled", "autostart_disabled"), ("schedule_enabled", "schedule_disabled")]:
            with self.subTest(key=key):
                data = configuration()
                data[key] = False
                plan = gate.build_plan(at(2026, 11, 13, 18, 30), loader_for(data))
                self.assertFalse(plan.due_now)
                self.assertEqual(plan.reason, expected)

    def test_missing_hours_never_power_off(self):
        data = configuration()
        data["week"][4]["start_local"] = None
        data["week"][4]["end_local"] = None
        plan = gate.build_plan(at(2026, 11, 13, 18, 30), loader_for(data))
        self.assertFalse(plan.due_now)
        self.assertEqual(plan.reason, "working_day_without_hours")

    def test_unconfigured_sunday_override_not_wakeable(self):
        data = configuration()
        data["overrides"] = [{"date": "2026-11-15", "enabled": True}]
        plan = gate.build_plan(at(2026, 11, 14, 18, 30), loader_for(data))
        self.assertEqual(plan.next_wake_local, "2026-11-16T08:00:00+01:00")

    def test_daylight_saving_rules(self):
        self.assertEqual(
            gate.local_wall_time(datetime(2027, 10, 31).date(), "02:30").fold, 0
        )
        with self.assertRaises(ValueError):
            gate.local_wall_time(datetime(2027, 3, 28).date(), "02:30")

    def test_invalid_source_fails_closed(self):
        with self.assertRaises(ValueError):
            gate.build_plan(datetime(2026, 11, 13, 18, 30), self.loader)

    def test_rollover_rejects_revision_change(self):
        def mismatch(year):
            entry = self.loader(year)
            if year == 2027:
                entry["revision"] = 4
            return entry
        with self.assertRaises(ValueError):
            gate.build_plan(at(2026, 12, 31, 18, 30), mismatch)

    def test_clock_timezone_conversion(self):
        plan = gate.build_plan(at(2026, 11, 13, 18, 30).astimezone(timezone.utc), self.loader)
        self.assertTrue(plan.due_now)

    def test_plan_and_non_due_tick_cannot_touch_hardware(self):
        from unittest.mock import patch
        due = gate.build_plan(at(2026, 11, 13, 18, 30), self.loader)
        not_due = gate.build_plan(at(2026, 11, 13, 18, 29), self.loader)
        with patch.object(gate, "trusted_existing_shutdown") as hardware:
            with patch.object(gate, "build_plan", return_value=due):
                with patch.object(sys, "argv", ["wvc-autostart-gate.py", "plan"]):
                    self.assertEqual(gate.main(), 0)
            with patch.object(gate, "build_plan", return_value=not_due):
                with patch.object(sys, "argv", ["wvc-autostart-gate.py", "tick"]):
                    self.assertEqual(gate.main(), 0)
            hardware.assert_not_called()

    def test_due_tick_delegates_to_existing_power_script_once(self):
        from unittest.mock import patch
        due = gate.build_plan(at(2026, 11, 13, 18, 30), self.loader)
        with patch.object(gate, "trusted_existing_shutdown") as hardware:
            with patch.object(gate, "build_plan", return_value=due):
                with patch.object(sys, "argv", ["wvc-autostart-gate.py", "tick"]):
                    self.assertEqual(gate.main(), 0)
            hardware.assert_called_once()
            wake, = hardware.call_args.args
            self.assertEqual(wake.isoformat(), "2026-11-14T08:00:00+01:00")

    def test_no_next_working_day_never_shutdown(self):
        data = configuration()
        for day in data["week"]:
            day["enabled"] = False
        plan = gate.build_plan(at(2026, 11, 13, 18, 30), loader_for(data))
        self.assertFalse(plan.due_now)
        self.assertEqual(plan.reason, "non_working_day")


if __name__ == "__main__":
    unittest.main()
