from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ventilation_core.calendar import (
    CalendarConfig,
    CalendarEngine,
    CalendarMode,
    CalendarPhase,
    CalendarProfile,
    CalendarRule,
    CalendarRuleKind,
    resolve_calendar,
)
from ventilation_core.infrastructure.sqlite_calendar_store import SqliteCalendarStore


def base_config() -> CalendarConfig:
    return CalendarConfig(
        timezone="Europe/Warsaw",
        profiles=(
            CalendarProfile("WORK", CalendarMode.AUTO, preventilation_minutes=30, purge_minutes=30),
            CalendarProfile("SERVICE", CalendarMode.FIXED, fixed_supply_pct=35, fixed_extract_pct=40),
            CalendarProfile("CLOSED", CalendarMode.OFF),
        ),
        rules=(
            CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
            CalendarRule("workdays", CalendarRuleKind.WEEKLY, "WORK", weekdays=(1, 2, 3, 4, 5), start_minute=7 * 60, end_minute=17 * 60),
        ),
    )


class CalendarResolverTest(unittest.TestCase):
    def test_preventilation_active_purge_and_next_wake(self) -> None:
        config = base_config()
        pre = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 4, 45, tzinfo=timezone.utc))
        self.assertEqual(pre.phase, CalendarPhase.PREVENTILATION)
        self.assertEqual(pre.effective_mode, CalendarMode.AUTO)
        self.assertEqual(pre.next_transition_reason, "START_ACTIVE")

        active = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(active.phase, CalendarPhase.ACTIVE)
        self.assertEqual(active.rule_source, CalendarRuleKind.WEEKLY)

        purge = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 15, 15, tzinfo=timezone.utc))
        self.assertEqual(purge.phase, CalendarPhase.PURGE)
        self.assertEqual(purge.next_transition_reason, "END_PURGE")

        night = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(night.phase, CalendarPhase.INACTIVE)
        self.assertEqual(night.effective_mode, CalendarMode.OFF)
        self.assertTrue(str(night.next_wake).startswith("2026-08-28T06:30:00"))

    def test_date_exception_outranks_weekly_and_skips_holiday(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=base_config().profiles,
            rules=base_config().rules + (
                CalendarRule(
                    "holiday",
                    CalendarRuleKind.DATE_EXCEPTION,
                    "CLOSED",
                    start_date=datetime(2026, 8, 28).date(),
                    end_date=datetime(2026, 8, 28).date(),
                ),
            ),
        )
        state = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc))
        self.assertTrue(str(state.next_wake).startswith("2026-08-31T06:30:00"))

    def test_date_range_outranks_weekly(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=base_config().profiles,
            rules=base_config().rules + (
                CalendarRule(
                    "vacation",
                    CalendarRuleKind.DATE_RANGE,
                    "CLOSED",
                    start_date=datetime(2026, 8, 24).date(),
                    end_date=datetime(2026, 8, 30).date(),
                ),
            ),
        )
        state = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(state.phase, CalendarPhase.INACTIVE)
        self.assertEqual(state.rule_source, CalendarRuleKind.DATE_RANGE)
        self.assertEqual(state.effective_profile, "CLOSED")

    def test_multiple_windows_one_day(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=base_config().profiles,
            rules=(
                CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
                CalendarRule("morning", CalendarRuleKind.WEEKLY, "WORK", weekdays=(4,), start_minute=7 * 60, end_minute=12 * 60),
                CalendarRule("afternoon", CalendarRuleKind.WEEKLY, "WORK", weekdays=(4,), start_minute=13 * 60, end_minute=17 * 60),
            ),
        )
        lunch = resolve_calendar(config, now_utc=datetime(2026, 8, 27, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(lunch.phase, CalendarPhase.PREVENTILATION)
        self.assertEqual(lunch.rule_id, "afternoon")

    def test_overnight_window(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=(CalendarProfile("NIGHT", CalendarMode.AUTO), CalendarProfile("CLOSED", CalendarMode.OFF)),
            rules=(
                CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
                CalendarRule("night", CalendarRuleKind.WEEKLY, "NIGHT", weekdays=(5,), start_minute=22 * 60, end_minute=2 * 60),
            ),
        )
        state = resolve_calendar(config, now_utc=datetime(2026, 8, 21, 22, 30, tzinfo=timezone.utc))
        self.assertEqual(state.phase, CalendarPhase.ACTIVE)

    def test_dst_fall_back_is_timezone_aware(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=(CalendarProfile("WORK", CalendarMode.AUTO), CalendarProfile("CLOSED", CalendarMode.OFF)),
            rules=(
                CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
                CalendarRule("sunday", CalendarRuleKind.WEEKLY, "WORK", weekdays=(7,), start_minute=2 * 60, end_minute=4 * 60),
            ),
        )
        first = resolve_calendar(config, now_utc=datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))
        second = resolve_calendar(config, now_utc=datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc))
        self.assertEqual(first.phase, CalendarPhase.ACTIVE)
        self.assertEqual(second.phase, CalendarPhase.ACTIVE)

    def test_leap_day_exception(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=(CalendarProfile("SPECIAL", CalendarMode.AUTO), CalendarProfile("CLOSED", CalendarMode.OFF)),
            rules=(
                CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
                CalendarRule("leap", CalendarRuleKind.DATE_EXCEPTION, "SPECIAL", start_date=datetime(2028, 2, 29).date(), end_date=datetime(2028, 2, 29).date(), start_minute=8 * 60, end_minute=9 * 60),
            ),
        )
        state = resolve_calendar(config, now_utc=datetime(2028, 2, 29, 7, 30, tzinfo=timezone.utc))
        self.assertEqual(state.phase, CalendarPhase.ACTIVE)
        self.assertEqual(state.rule_source, CalendarRuleKind.DATE_EXCEPTION)

    def test_overlapping_same_priority_rules_fail(self) -> None:
        config = CalendarConfig(
            timezone="Europe/Warsaw",
            profiles=base_config().profiles,
            rules=(
                CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
                CalendarRule("a", CalendarRuleKind.WEEKLY, "WORK", weekdays=(1,), start_minute=7 * 60, end_minute=12 * 60),
                CalendarRule("b", CalendarRuleKind.WEEKLY, "WORK", weekdays=(1,), start_minute=11 * 60, end_minute=15 * 60),
            ),
        )
        with self.assertRaisesRegex(ValueError, "overlapping"):
            resolve_calendar(config, now_utc=datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc))


class CalendarPersistenceTest(unittest.TestCase):
    def test_atomic_versioned_config_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            store = SqliteCalendarStore(path, initial_config=base_config())
            config, revision = store.load()
            self.assertEqual(revision, 1)
            self.assertEqual(config.timezone, "Europe/Warsaw")
            self.assertEqual(store.replace(config), 2)
            store.close()

            store = SqliteCalendarStore(path)
            restored, revision = store.load()
            self.assertEqual(revision, 2)
            self.assertEqual(restored.to_dict(), config.to_dict())
            store.close()

    def test_engine_failure_is_fail_safe_unavailable(self) -> None:
        class BrokenStore:
            def load(self):
                raise RuntimeError("calendar db unavailable")
            def replace(self, config):
                raise RuntimeError("calendar db unavailable")
            def close(self):
                return

        state = CalendarEngine(BrokenStore()).resolve(datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc))
        self.assertFalse(state.available)
        self.assertIn("calendar db unavailable", state.last_error)


if __name__ == "__main__":
    unittest.main()
