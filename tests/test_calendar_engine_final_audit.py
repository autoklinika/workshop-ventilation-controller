from __future__ import annotations

import copy
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


def _valid_json_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "timezone": "Europe/Warsaw",
        "profiles": [
            {
                "profile_id": "WORK",
                "mode": "AUTO",
                "preventilation_minutes": 30,
                "purge_minutes": 30,
                "minimum_supply_pct": None,
                "minimum_extract_pct": None,
                "fixed_supply_pct": None,
                "fixed_extract_pct": None,
                "label": "Work",
            },
            {
                "profile_id": "CLOSED",
                "mode": "OFF",
                "preventilation_minutes": 0,
                "purge_minutes": 0,
                "minimum_supply_pct": None,
                "minimum_extract_pct": None,
                "fixed_supply_pct": None,
                "fixed_extract_pct": None,
                "label": "Closed",
            },
        ],
        "rules": [
            {
                "rule_id": "default",
                "kind": "DEFAULT",
                "profile_id": "CLOSED",
                "weekdays": [],
                "months": [],
                "start_date": None,
                "end_date": None,
                "start_local": None,
                "end_local": None,
                "enabled": True,
                "label": "Default",
            },
            {
                "rule_id": "workdays",
                "kind": "WEEKLY",
                "profile_id": "WORK",
                "weekdays": [1, 2, 3, 4, 5],
                "months": [],
                "start_date": None,
                "end_date": None,
                "start_local": "07:00",
                "end_local": "17:00",
                "enabled": True,
                "label": "Workdays",
            },
        ],
    }


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

    def test_schema_version_boolean_is_not_accepted_as_integer_one(self) -> None:
        payload = _valid_json_payload()
        payload["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "schema_version"):
            CalendarConfig.from_dict(payload)

    def test_profile_minutes_are_not_coerced_from_boolean_or_text(self) -> None:
        for invalid in (True, "30"):
            with self.subTest(invalid=invalid):
                payload = copy.deepcopy(_valid_json_payload())
                payload["profiles"][0]["preventilation_minutes"] = invalid  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, "preventilation_minutes"):
                    CalendarConfig.from_dict(payload)

    def test_weekdays_are_not_coerced_from_boolean_or_text(self) -> None:
        for invalid in ([True], ["1"]):
            with self.subTest(invalid=invalid):
                payload = copy.deepcopy(_valid_json_payload())
                payload["rules"][1]["weekdays"] = invalid  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, "weekdays"):
                    CalendarConfig.from_dict(payload)

    def test_ids_and_time_fields_require_json_text(self) -> None:
        payload = copy.deepcopy(_valid_json_payload())
        payload["profiles"][0]["profile_id"] = 123  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "profile_id"):
            CalendarConfig.from_dict(payload)

        payload = copy.deepcopy(_valid_json_payload())
        payload["rules"][1]["start_local"] = 700  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "time must be HH:MM text"):
            CalendarConfig.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
