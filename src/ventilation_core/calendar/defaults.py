from __future__ import annotations

from .model import (
    DEFAULT_TIMEZONE,
    CalendarConfig,
    CalendarMode,
    CalendarProfile,
    CalendarRule,
    CalendarRuleKind,
)


def default_calendar_config() -> CalendarConfig:
    """Return the neutral first-boot calendar.

    No operating hours are invented. The system starts in a deterministic
    STANDBY context until an operator stores an explicit calendar.
    """

    return CalendarConfig(
        timezone=DEFAULT_TIMEZONE,
        profiles=(
            CalendarProfile(
                profile_id="DEFAULT_STANDBY",
                mode=CalendarMode.STANDBY,
                label="Domyślny stan oczekiwania",
            ),
        ),
        rules=(
            CalendarRule(
                rule_id="DEFAULT_STANDBY",
                kind=CalendarRuleKind.DEFAULT,
                profile_id="DEFAULT_STANDBY",
                label="Domyślna reguła bez godzin pracy",
            ),
        ),
    )
