"""Non-actuating tests for universal calendar RTC / scheduled AUTO continuity."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from calendar import isleap
import importlib.util
import json
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "deploy/cm5/wvc-schedule-keeper.py"
spec = importlib.util.spec_from_file_location("wvc_schedule_keeper_test", PATH)
keeper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keeper)
W = keeper.WARSAW


def make_calendar(year: int, *, saturday=False, sunday=False, exceptions=None,
                  start="08:00", end="18:30", enabled=True, revision=4):
    exceptions = exceptions or {}
    rows = []
    for day_number in range(366 if isleap(year) else 365):
        day = date(year, 1, 1) + timedelta(days=day_number)
        works = day.isoweekday() <= 5 or (day.isoweekday() == 6 and saturday) or (
            day.isoweekday() == 7 and sunday)
        works = exceptions.get(day.isoformat(), works)
        rows.append({"date": day.isoformat(), "weekday": day.isoweekday(),
                     "enabled": works, "start_local": start if works else None,
                     "end_local": end if works else None})
    return {"autostart": {"available": True, "year": year, "revision": revision,
                         "config": {"enabled": enabled, "schedule_enabled": True},
                         "days": rows}}


def source(docs):
    return lambda year: docs[year]


def local(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=W)


def base_state(hold_reason="MANUAL_COMMAND_stop"):
    return {"active_auto": {"enabled": True, "active": False, "mode": "MANUAL",
                            "hold": True, "hold_reason": hold_reason,
                            "fault_latched": False, "operator_action": None},
            "hardware_ready": True, "output_state_known": True,
            "tacho": {"ready": True, "worker_alive": True},
            "aero_bus": {"ready": True, "online": True, "usable": True},
            "sensor_bus": {"nodes": [
                {"slave_address": addr, "online": True, "usable": True,
                 "measurement_valid": True, "measurement_stale": False}
                for addr in (1, 2)]}, "active_alarms": []}


class CalendarKeeperTest(unittest.TestCase):
    def test_weekend_manual_boot_preserves_monday_start(self):
        now = local(2026, 11, 14, 8, 32)
        result = keeper.plan(now, source({2026: make_calendar(2026)}))
        self.assertEqual(result["next_wake_local"], "2026-11-16T08:00:00+01:00")
        self.assertFalse(result["start_due"])

    def test_holiday_manual_boot_selects_next_calendar_day(self):
        doc = make_calendar(2026, exceptions={"2026-12-24": False, "2026-12-25": False})
        result = keeper.plan(local(2026, 12, 23, 18, 31), source({2026: doc}))
        self.assertEqual(result["next_wake_local"], "2026-12-28T08:00:00+01:00")

    def test_manual_override_enable_holiday(self):
        doc = make_calendar(2026, exceptions={"2026-11-15": True})
        result = keeper.plan(local(2026, 11, 14, 9, 0), source({2026: doc}))
        self.assertEqual(result["next_wake_local"], "2026-11-15T08:00:00+01:00")

    def test_before_scheduled_start_wakes_today(self):
        result = keeper.plan(local(2026, 11, 16, 7, 30), source({2026: make_calendar(2026)}))
        self.assertEqual(result["next_wake_local"], "2026-11-16T08:00:00+01:00")
        self.assertFalse(result["start_due"])

    def test_running_at_start_arms_next_day_and_starts(self):
        result = keeper.plan(local(2026, 11, 16, 8, 1), source({2026: make_calendar(2026)}))
        self.assertTrue(result["start_due"])
        self.assertEqual(result["next_wake_local"], "2026-11-17T08:00:00+01:00")

    def test_running_through_start_window_not_repeated_later(self):
        doc = {2026: make_calendar(2026)}
        self.assertTrue(keeper.plan(local(2026, 11, 16, 8, 19), source(doc))["start_due"])
        self.assertFalse(keeper.plan(local(2026, 11, 16, 8, 20), source(doc))["start_due"])

    def test_year_rollover_uses_next_year_calendar(self):
        docs = {2026: make_calendar(2026, exceptions={"2026-12-31": False}),
                2027: make_calendar(2027, exceptions={"2027-01-01": False})}
        result = keeper.plan(local(2026, 12, 30, 18, 30), source(docs))
        self.assertEqual(result["next_wake_local"], "2027-01-04T08:00:00+01:00")

    def test_disabled_schedule_prevents_start(self):
        doc = make_calendar(2026, enabled=False)
        result = keeper.plan(local(2026, 11, 16, 8, 0), source({2026: doc}))
        self.assertFalse(result["start_due"])
        self.assertIsNone(result["next_wake_local"])

    def test_corrupt_calendar_fails_closed(self):
        doc = make_calendar(2026)
        doc["autostart"]["days"].pop()
        with self.assertRaises(ValueError):
            keeper.plan(local(2026, 11, 16, 8, 0), source({2026: doc}))

    def test_no_rtc_write_when_alarm_already_correct(self):
        now = local(2026, 11, 16, 8, 0)
        with patch.object(keeper, "synced_clock", return_value=True), \
             patch.object(keeper, "RTC_ALARM") as alarm, \
             patch.object(keeper, "trusted_file") as trust:
            alarm.read_text.return_value = str(int(now.timestamp()))
            self.assertEqual(keeper.reconcile_rtc(now.isoformat(), active_schedule=True), "already_armed")
            alarm.write_text.assert_not_called()
            trust.assert_not_called()

    def test_disabled_calendar_clears_pending_alarm(self):
        with patch.object(keeper, "synced_clock", return_value=True), \
             patch.object(keeper, "RTC_ALARM") as alarm:
            alarm.read_text.return_value = "1794812400"
            self.assertEqual(keeper.reconcile_rtc(None, active_schedule=False), "cleared_disabled")
            alarm.write_text.assert_called_once_with("0\n", encoding="ascii")

    def test_clock_unsynced_never_writes_rtc(self):
        with patch.object(keeper, "synced_clock", return_value=False), \
             patch.object(keeper, "RTC_ALARM") as alarm:
            with self.assertRaises(RuntimeError):
                keeper.reconcile_rtc("2026-11-16T08:00:00+01:00", active_schedule=True)
            alarm.write_text.assert_not_called()

    def test_ordinary_manual_expires_at_next_scheduled_start(self):
        start = local(2026, 11, 16, 8, 0)
        old = {"reason": "OPERATOR_SELECTED_MANUAL", "at": "2026-11-14T12:00:00+01:00",
               "fault_latched": False}
        with patch.object(keeper, "kernel_boot_utc", return_value=start.astimezone(timezone.utc)):
            self.assertEqual(keeper.safe_to_resume(base_state("OPERATOR_SELECTED_MANUAL"), old, start), "ready")

    def test_same_day_manual_change_after_start_not_overridden(self):
        start = local(2026, 11, 16, 8, 0)
        hold = {"reason": "OPERATOR_SELECTED_MANUAL", "at": "2026-11-16T08:03:00+01:00",
                "fault_latched": False}
        with patch.object(keeper, "kernel_boot_utc", return_value=(start - timedelta(days=1)).astimezone(timezone.utc)):
            self.assertEqual(keeper.safe_to_resume(base_state("OPERATOR_SELECTED_MANUAL"), hold, start),
                             "rejected_manual_or_unknown_hold")

    def test_explicit_hold_and_fault_never_cleared(self):
        start = local(2026, 11, 16, 8, 0)
        for reason in ("EXPLICIT_OPERATOR_HOLD", "SEN55_1_UNAVAILABLE"):
            hold = {"reason": reason, "at": "2026-11-14T12:00:00+01:00"}
            with patch.object(keeper, "kernel_boot_utc", return_value=start.astimezone(timezone.utc)):
                self.assertEqual(keeper.safe_to_resume(base_state(reason), hold, start),
                                 "rejected_manual_or_unknown_hold")
        state = base_state()
        state["active_auto"]["fault_latched"] = True
        with patch.object(keeper, "kernel_boot_utc", return_value=start.astimezone(timezone.utc)):
            self.assertEqual(keeper.safe_to_resume(state, {"reason": "MANUAL_COMMAND_stop"}, start),
                             "rejected_fault")

    def test_hardware_not_ready_does_not_resume(self):
        start = local(2026, 11, 16, 8, 0)
        hold = {"reason": "MANUAL_COMMAND_stop", "at": "2026-11-14T12:00:00+01:00"}
        state = base_state()
        state["sensor_bus"]["nodes"][1]["usable"] = False
        with patch.object(keeper, "kernel_boot_utc", return_value=start.astimezone(timezone.utc)):
            self.assertEqual(keeper.safe_to_resume(state, hold, start), "waiting_sensor_2")

    def test_claim_guards_later_manual_stop(self):
        self.assertTrue(keeper.claim_matches(
            {"schema": 1, "start_local": "2026-11-16T08:00:00+01:00", "revision": 4},
            "2026-11-16T08:00:00+01:00", 4))
        self.assertFalse(keeper.claim_matches(
            {"schema": 1, "start_local": "2026-11-16T08:00:00+01:00", "revision": 4},
            "2026-11-17T08:00:00+01:00", 4))

    def test_planned_start_resumes_only_once(self):
        start = local(2026, 11, 16, 8, 0)
        info = keeper.plan(start, source({2026: make_calendar(2026)}))
        hold = json.dumps({"reason": "MANUAL_COMMAND_stop",
                           "at": "2026-11-14T12:00:00+01:00",
                           "fault_latched": False})
        calls = []
        def request(cmd):
            calls.append(cmd["command"])
            if cmd["command"] == "status":
                return {"state": base_state()}
            return {"active_auto": {"active": True, "hold": False}}
        with patch.object(keeper, "load_claim", return_value=None), \
             patch.object(keeper, "OLD_TICKET") as ticket, \
             patch.object(keeper, "HOLD_FILE") as hold_path, \
             patch.object(keeper, "core_request", side_effect=request), \
             patch.object(keeper, "record_claim") as claim, \
             patch.object(keeper, "kernel_boot_utc", return_value=(start - timedelta(hours=1)).astimezone(timezone.utc)):
            ticket.exists.return_value = False
            hold_path.read_text.return_value = hold
            self.assertEqual(keeper.maybe_start_auto(info), "resumed_auto")
            self.assertEqual(calls, ["status", "auto-resume"])
            claim.assert_called_once_with("2026-11-16T08:00:00+01:00", 4, "attempted")
        with patch.object(keeper, "load_claim", return_value={
                "schema": 1, "start_local": "2026-11-16T08:00:00+01:00", "revision": 4}), \
             patch.object(keeper, "core_request") as request:
            self.assertEqual(keeper.maybe_start_auto(info), "already_processed")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
