from __future__ import annotations

import unittest

from ventilation_core.calendar import (
    CalendarConfig,
    CalendarEngine,
    CalendarMode,
    CalendarProfile,
    CalendarRule,
    CalendarRuleKind,
)


class _RecordingStore:
    def __init__(self) -> None:
        self.replace_calls = 0

    def load(self):
        raise AssertionError("load is not expected in validation-only test")

    def replace(self, config):
        self.replace_calls += 1
        return 1

    def close(self):
        return


class CalendarEngineFinalAuditTest(unittest.TestCase):
    def test_maximum_guard_windows_detect_conflict_three_rule_dates_apart(self) -> None:
        store = _RecordingStore()
        engine = CalendarEngine(store)
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=(
                CalendarProfile("LONG_PURGE", CalendarMode.AUTO, purge_minutes=1440),
                CalendarProfile("LONG_PRE", CalendarMode.AUTO, preventilation_minutes=1440),
                CalendarProfile("CLOSED", CalendarMode.OFF),
            ),
            rules=(
                CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
                CalendarRule(
                    "monday-long",
                    CalendarRuleKind.WEEKLY,
                    "LONG_PURGE",
                    weekdays=(1,),
                    start_minute=23 * 60,
                    end_minute=22 * 60,
                ),
                CalendarRule(
                    "thursday-early",
                    CalendarRuleKind.WEEKLY,
                    "LONG_PRE",
                    weekdays=(4,),
                    start_minute=0,
                    end_minute=60,
                ),
            ),
        )

        with self.assertRaisesRegex(ValueError, "start-date offset \\+3d"):
            engine.replace_configuration(config.to_dict())
        self.assertEqual(store.replace_calls, 0)


if __name__ == "__main__":
    unittest.main()
