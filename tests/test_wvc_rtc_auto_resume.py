"""Non-actuating tests for one-shot scheduled RTC AUTO restoration.

These tests never send commands to a real core nor operate GPIO/RTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "deploy/cm5/wvc-rtc-auto-resume.py"
spec = importlib.util.spec_from_file_location("wvc_rtc_auto_resume_test", HELPER)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)

OLD_BOOT = "11111111-2222-3333-4444-555555555555"
NEW_BOOT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
WAKE = datetime(2026, 11, 14, 7, 0, tzinfo=timezone.utc)
CREATED = datetime(2026, 11, 13, 17, 30, tzinfo=timezone.utc)


def marker() -> dict:
    return helper.make_ticket(WAKE, 4, now=CREATED, source_boot_id=OLD_BOOT)


def ready_state(reason: str = "MANUAL_COMMAND_aero-speed") -> dict:
    return {
        "active_auto": {
            "enabled": True, "active": False, "hold": True,
            "mode": "MANUAL", "hold_reason": reason,
            "fault_latched": False, "operator_action": None,
        },
        "active_alarms": [],
        "hardware_ready": True,
        "output_state_known": True,
        "tacho": {"ready": True, "worker_alive": True},
        "aero_bus": {"ready": True, "online": True, "usable": True},
        "sensor_bus": {"nodes": [
            {"slave_address": address, "online": True, "usable": True,
             "measurement_valid": True, "measurement_stale": False}
            for address in (1, 2)
        ]},
    }


def autostart_doc() -> dict:
    return {
        "autostart": {
            "available": True, "revision": 4, "year": 2026,
            "config": {"enabled": True, "schedule_enabled": True},
            "days": [{"date": "2026-11-14", "enabled": True, "start_local": "08:00"}],
        },
    }


class ScheduledAutoResumeTests(unittest.TestCase):
    def test_only_pre_shutdown_auto_produces_permission(self):
        state = ready_state()
        state["active_auto"].update(active=True, mode="AUTO", hold=False)
        self.assertTrue(helper.auto_pre_shutdown_active(state))
        for modification in (
            {"active": False}, {"mode": "MANUAL"}, {"hold": True}, {"fault_latched": True},
        ):
            temp = ready_state()
            temp["active_auto"].update(active=True, mode="AUTO", hold=False)
            temp["active_auto"].update(modification)
            self.assertFalse(helper.auto_pre_shutdown_active(temp))

    def test_ticket_validation_and_replay_protection(self):
        ticket = marker()
        self.assertEqual(helper.validate_ticket(ticket), ticket)
        self.assertEqual(
            helper.ticket_wake_allowed(
                ticket, now=WAKE + timedelta(minutes=3),
                current_boot_id=OLD_BOOT, boot_start=WAKE,
            ), "same_boot"
        )
        self.assertEqual(
            helper.ticket_wake_allowed(
                ticket, now=WAKE + timedelta(minutes=3),
                current_boot_id=NEW_BOOT, boot_start=WAKE,
            ), "expected_window"
        )
        self.assertEqual(
            helper.ticket_wake_allowed(
                ticket, now=WAKE + timedelta(minutes=3),
                current_boot_id=NEW_BOOT, boot_start=WAKE - timedelta(minutes=20),
            ), "outside_boot_window"
        )
        self.assertEqual(
            helper.ticket_wake_allowed(
                ticket, now=WAKE + timedelta(minutes=23),
                current_boot_id=NEW_BOOT, boot_start=WAKE,
            ), "outside_expected_window"
        )

    def test_reject_oversized_or_malformed_ticket(self):
        ticket = marker()
        for field, value in (
            ("schema_version", 2), ("calendar_revision", True),
            ("source_boot_id", "forged"), ("created_utc", "malformed"),
        ):
            changed = dict(ticket)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                helper.validate_ticket(changed)
        with self.assertRaises(ValueError):
            helper.make_ticket(WAKE, 4, now=WAKE + timedelta(minutes=1),
                               source_boot_id=OLD_BOOT)

    def test_explicit_manual_and_fault_hold_are_never_overridden(self):
        self.assertEqual(helper.resume_preflight(ready_state()), "ready")
        self.assertEqual(helper.resume_preflight(ready_state("MANUAL_COMMAND_stop")), "ready")
        for reason in ("OPERATOR_SELECTED_MANUAL", "EXPLICIT_OPERATOR_HOLD",
                       "SEN55_1_UNAVAILABLE", "BOOT_MANUAL_REQUIRES_EXPLICIT_AUTO_RESUME"):
            with self.subTest(reason=reason):
                self.assertEqual(
                    helper.resume_preflight(ready_state(reason)),
                    "rejected_operator_or_unknown_hold",
                )
        state = ready_state()
        state["active_auto"]["fault_latched"] = True
        self.assertEqual(helper.resume_preflight(state), "rejected_fault")
        state = ready_state()
        state["active_alarms"] = [{"severity": "CRITICAL"}]
        self.assertEqual(helper.resume_preflight(state), "rejected_critical_alarm")

    def test_missing_hardware_or_sensors_prevents_auto(self):
        modifications = [
            ("hardware_ready", False, "waiting_dac"),
            ("tacho", {"ready": False, "worker_alive": True}, "waiting_tacho"),
            ("aero_bus", {"ready": True, "online": False, "usable": False}, "waiting_aero"),
        ]
        for field, value, expected in modifications:
            with self.subTest(field=field):
                state = ready_state()
                state[field] = value
                self.assertEqual(helper.resume_preflight(state), expected)
        state = ready_state()
        state["sensor_bus"]["nodes"][1]["measurement_stale"] = True
        self.assertEqual(helper.resume_preflight(state), "waiting_sensor_2")

    def test_autostart_calendar_must_match_wake_date_and_revision(self):
        ticket = marker()
        self.assertTrue(helper.autostart_matches(ticket, autostart_doc()))
        for key, value in (
            ("revision", 5), ("year", 2027), ("available", False),
        ):
            response = autostart_doc()
            response["autostart"][key] = value
            self.assertFalse(helper.autostart_matches(ticket, response))
        response = autostart_doc()
        response["autostart"]["config"]["enabled"] = False
        self.assertFalse(helper.autostart_matches(ticket, response))
        response = autostart_doc()
        response["autostart"]["days"][0]["start_local"] = "09:00"
        self.assertFalse(helper.autostart_matches(ticket, response))

    def test_boot_service_consumes_ticket_then_calls_existing_resume(self):
        calls = []
        def fake_request(payload):
            calls.append(payload["command"])
            if payload["command"] == "autostart":
                return autostart_doc()
            if payload["command"] == "status":
                return {"state": ready_state()}
            if payload["command"] == "auto-resume":
                return {"active_auto": {"active": True, "hold": False}}
            raise AssertionError(payload)
        with patch.object(helper.os, "geteuid", return_value=0), \
             patch.object(helper, "read_ticket", return_value=marker()), \
             patch.object(helper, "boot_id", return_value=NEW_BOOT), \
             patch.object(helper, "synced_clock", return_value=True), \
             patch.object(helper, "ticket_wake_allowed", return_value="expected_window"), \
             patch.object(helper, "core_request", side_effect=fake_request), \
             patch.object(helper, "clear_ticket", side_effect=lambda path: calls.append("consumed")):
            self.assertEqual(helper.scheduled_resume(), "resumed_auto")
        self.assertEqual(calls, ["autostart", "status", "consumed", "auto-resume"])

    def test_scheduled_service_rejects_manual_no_auto_command(self):
        calls = []
        def fake_request(payload):
            calls.append(payload["command"])
            if payload["command"] == "autostart":
                return autostart_doc()
            if payload["command"] == "status":
                return {"state": ready_state("OPERATOR_SELECTED_MANUAL")}
            raise AssertionError("auto-resume should be blocked")
        with patch.object(helper.os, "geteuid", return_value=0), \
             patch.object(helper, "read_ticket", return_value=marker()), \
             patch.object(helper, "boot_id", return_value=NEW_BOOT), \
             patch.object(helper, "synced_clock", return_value=True), \
             patch.object(helper, "ticket_wake_allowed", return_value="expected_window"), \
             patch.object(helper, "core_request", side_effect=fake_request), \
             patch.object(helper, "clear_ticket") as clear:
            self.assertEqual(helper.scheduled_resume(), "rejected_operator_or_unknown_hold")
            clear.assert_called_once()
        self.assertEqual(calls, ["autostart", "status"])

    def test_no_ticket_no_actuation(self):
        with patch.object(helper.os, "geteuid", return_value=0), \
             patch.object(helper, "read_ticket", return_value=None), \
             patch.object(helper, "core_request") as call:
            self.assertEqual(helper.scheduled_resume(), "no_ticket")
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
