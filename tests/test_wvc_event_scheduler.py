"""Event-driven schedule tests; never invoke real systemd/RTC/actuators."""
from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib.util
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wvc_keeper_event_test", ROOT / "deploy/cm5/wvc-schedule-keeper.py")
keeper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = keeper
spec.loader.exec_module(keeper)

from ventilation_core.domain.autostart import default_config, validate_config, year_days


def source(config):
    def get(year):
        return {"autostart": {"available": True, "year": year, "revision": 4,
                "config": config, "days": year_days(config, year)}}
    return get


def default_active():
    config = default_config()
    config["enabled"] = True
    config["schedule_enabled"] = True
    for day in config["week"]:
        day["start_local"], day["end_local"] = "08:00", "18:30"
    config["week"][5]["enabled"] = False
    config["week"][6]["enabled"] = False
    return validate_config(config)


class EventSchedulerTests(unittest.TestCase):
    def test_next_close_and_start_for_weekend(self):
        config = default_active()
        sat = datetime(2026, 11, 14, 9, 0, tzinfo=keeper.WARSAW)
        result = keeper.plan(sat, source(config))
        self.assertIsNone(result["start_today_local"])
        self.assertEqual(result["next_wake_local"], "2026-11-16T08:00:00+01:00")
        self.assertEqual(result["next_close_local"], "2026-11-16T18:30:00+01:00")
        self.assertFalse(result["start_due"])

    def test_today_start_and_same_day_close(self):
        info = keeper.plan(datetime(2026, 11, 16, 7, 30, tzinfo=keeper.WARSAW), source(default_active()))
        self.assertEqual(info["next_wake_local"], "2026-11-16T08:00:00+01:00")
        self.assertEqual(info["next_close_local"], "2026-11-16T18:30:00+01:00")

    def test_after_start_close_today_start_tomorrow(self):
        info = keeper.plan(datetime(2026, 11, 16, 8, 5, tzinfo=keeper.WARSAW), source(default_active()))
        self.assertEqual(info["next_wake_local"], "2026-11-17T08:00:00+01:00")
        self.assertEqual(info["next_close_local"], "2026-11-16T18:30:00+01:00")
        self.assertTrue(info["start_due"])

    def test_close_timer_points_to_existing_power_gate(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            recorded = []
            def pretend(command, **_):
                recorded.append(command)
                class R:
                    returncode = 0
                    stdout = "Running timer"
                return R()
            with patch.object(keeper, "STATE_DIR", directory), \
                 patch.object(keeper, "TIMER_STATE", directory / "start.json"), \
                 patch.object(keeper, "CLOSE_TIMER_STATE", directory / "close.json"), \
                 patch.object(keeper, "validate_state_directory"), \
                 patch.object(keeper.subprocess, "run", side_effect=pretend):
                self.assertEqual(keeper.schedule_one_event("2026-11-16T18:30:00+01:00", kind="close"), "scheduled")
            self.assertEqual(len(recorded), 1)
            self.assertIn("/usr/local/libexec/wvc-autostart-gate.py", recorded[0])
            self.assertIn("--on-calendar=2026-11-16 18:30:00 Europe/Warsaw", recorded[0])
            state = json.loads((directory / "close.json").read_text())
            self.assertTrue(state["unit"].startswith("wvc-scheduled-close-20261116-1830-"))

    def test_start_timer_calls_boot_safe_keeper_once(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            commands = []
            def pretend(cmd, **_):
                commands.append(cmd)
                class R:
                    returncode = 0
                    stdout = "Running timer"
                return R()
            with patch.object(keeper, "STATE_DIR", directory), \
                 patch.object(keeper, "TIMER_STATE", directory / "start.json"), \
                 patch.object(keeper, "CLOSE_TIMER_STATE", directory / "close.json"), \
                 patch.object(keeper, "validate_state_directory"), \
                 patch.object(keeper.subprocess, "run", side_effect=pretend):
                self.assertEqual(keeper.schedule_one_event("2026-11-16T08:00:00+01:00"), "scheduled")
            self.assertIn("/usr/local/libexec/wvc-schedule-keeper.py", commands[0])
            self.assertEqual(commands[0][-1], "start")

    def test_no_repeated_polling_actions_in_unit_files(self):
        deploy = ROOT / "deploy/systemd"
        self.assertFalse((deploy / "wvc-schedule-keeper.timer").exists())
        self.assertFalse((deploy / "wvc-schedule-keeper.service").exists())
        self.assertIn("PathModified=", (deploy / "wvc-schedule-change.path").read_text())
        self.assertIn("WantedBy=multi-user.target", (deploy / "wvc-schedule-boot.service").read_text())
        self.assertIn("wvc-schedule-keeper.py boot", (deploy / "wvc-schedule-boot.service").read_text())


if __name__ == "__main__":
    unittest.main()

class WebUiCalendarNotificationTests(unittest.TestCase):
    def test_successful_save_notifies_systemd_path_once(self):
        from ventilation_core.web.app import WebApplication
        from ventilation_core.domain.autostart import default_config
        import ventilation_core.web.app as web_module
        class FakeCore:
            def request(self, command):
                self.last = command
                return {'ok': True, 'autostart': {'revision': 5, 'available': True}}
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'autostart-changed.signal'
            marker.write_text('4\n')
            app = WebApplication(FakeCore())
            with patch.object(web_module, 'Path', return_value=marker):
                response = app.handle('POST', '/api/v1/autostart',
                                      {'year': 2026, 'expected_revision': 4,
                                       'config': default_config()})
            self.assertEqual(response.status, 200)
            self.assertEqual(marker.read_text(), '5\n')

    def test_failed_save_does_not_trigger_rtc_notification(self):
        from ventilation_core.web.app import WebApplication
        from ventilation_core.domain.autostart import default_config
        import ventilation_core.web.app as web_module
        class FakeCore:
            def request(self, command):
                return {'ok': False, 'error': 'revision conflict'}
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'autostart-changed.signal'
            marker.write_text('4\n')
            with patch.object(web_module, 'Path', return_value=marker):
                response = WebApplication(FakeCore()).handle(
                    'POST', '/api/v1/autostart',
                    {'year': 2026, 'expected_revision': 4, 'config': default_config()})
            self.assertNotEqual(response.status, 200)
            self.assertEqual(marker.read_text(), '4\n')

class EventChangeCancellationTests(unittest.TestCase):
    def test_calendar_change_cancels_old_start_and_close(self):
        from tempfile import TemporaryDirectory
        import subprocess
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            def run(cmd, **kwargs):
                calls.append(tuple(cmd))
                return subprocess.CompletedProcess(cmd, 0, stdout='Running as unit', stderr='')
            with patch.object(keeper, 'STATE_DIR', root), \
                 patch.object(keeper, 'TIMER_STATE', root/'start.json'), \
                 patch.object(keeper, 'CLOSE_TIMER_STATE', root/'close.json'), \
                 patch.object(keeper, 'validate_state_directory'), \
                 patch.object(keeper.subprocess, 'run', side_effect=run):
                keeper.schedule_one_event('2026-11-16T08:00:00+01:00', kind='start')
                keeper.schedule_one_event('2026-11-16T18:30:00+01:00', kind='close')
                keeper.schedule_one_event('2026-11-17T09:00:00+01:00', kind='start')
                keeper.schedule_one_event('2026-11-17T19:00:00+01:00', kind='close')
                keeper.schedule_one_event(None, kind='start')
                keeper.schedule_one_event(None, kind='close')
                # Re-enabling after OFF must not reject the persisted null unit.
                keeper.schedule_one_event('2026-11-18T09:00:00+01:00', kind='start')
                keeper.schedule_one_event('2026-11-18T19:00:00+01:00', kind='close')
            stopped = [arg for arg in calls if arg[0] == '/usr/bin/systemctl' and arg[1] == 'stop']
            self.assertEqual(len(stopped), 4)
            self.assertIn('20261118-0900', json.loads((root/'start.json').read_text())['unit'])
            self.assertIn('20261118-1900', json.loads((root/'close.json').read_text())['unit'])

    def test_scheduler_rejects_untrusted_target(self):
        with TemporaryDirectory() as tmp, \
             patch.object(keeper, 'TIMER_STATE', Path(tmp)/'start.json'), \
             patch.object(keeper, 'validate_state_directory'):
            with self.assertRaises(ValueError):
                keeper.schedule_one_event('2026-11-16T08:00:00', kind='start')
            with self.assertRaises(ValueError):
                keeper.schedule_one_event('2026-11-16T08:00:00+01:00', kind='restart')
