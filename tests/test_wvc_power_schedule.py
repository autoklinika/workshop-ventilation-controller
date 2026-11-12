import importlib.util
from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wvc_power_schedule", ROOT / "tools/wvc_power_schedule.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
TZ = ZoneInfo("Europe/Warsaw")


class WvcPowerScheduleTest(unittest.TestCase):
    def test_evening_wakes_next_morning(self):
        now = datetime(2026, 11, 12, 19, 0, tzinfo=TZ)
        self.assertEqual(MOD.next_wakeup(now), datetime(2026, 11, 13, 8, 0, tzinfo=TZ))

    def test_summer_daylight_savings(self):
        now = datetime(2027, 3, 27, 19, 0, tzinfo=TZ)
        wake = MOD.next_wakeup(now)
        self.assertEqual((wake.year, wake.month, wake.day, wake.hour), (2027, 3, 28, 8))
        self.assertEqual(wake.utcoffset().total_seconds(), 7200)

    def test_winter_daylight_savings(self):
        now = datetime(2027, 10, 30, 19, 0, tzinfo=TZ)
        wake = MOD.next_wakeup(now)
        self.assertEqual((wake.year, wake.month, wake.day, wake.hour), (2027, 10, 31, 8))
        self.assertEqual(wake.utcoffset().total_seconds(), 3600)

    def test_early_start_still_today(self):
        now = datetime(2026, 11, 13, 6, 30, tzinfo=TZ)
        self.assertEqual(MOD.next_wakeup(now), datetime(2026, 11, 13, 8, 0, tzinfo=TZ))

    def test_short_lead_rolls_to_tomorrow(self):
        now = datetime(2026, 11, 13, 7, 55, tzinfo=TZ)
        self.assertEqual(MOD.next_wakeup(now), datetime(2026, 11, 14, 8, 0, tzinfo=TZ))


if __name__ == "__main__":
    unittest.main()
