"""A non-actuating annual host-autostart plan for the Polish workshop calendar.

This model is intentionally independent of Calendar Engine (ventilation demand)
and of Power Scheduler (RTC/power authority).  Saving the plan cannot turn on
power scheduling or issue actuator commands.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Mapping

TIMEZONE = "Europe/Warsaw"
MIN_YEAR, MAX_YEAR = 2025, 2100
MAX_OVERRIDES = 512


def easter_sunday(year: int) -> date:
    """Gregorian computus valid for the years supported by this model."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def polish_holidays(year: int) -> dict[date, str]:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("year outside 2025..2100")
    easter = easter_sunday(year)
    result = {
        date(year, 1, 1): "Nowy Rok",
        date(year, 1, 6): "Trzech Króli",
        easter: "Wielkanoc",
        easter + timedelta(days=1): "Poniedziałek Wielkanocny",
        date(year, 5, 1): "Święto Pracy",
        date(year, 5, 3): "Święto Konstytucji 3 Maja",
        easter + timedelta(days=49): "Zesłanie Ducha Świętego",
        easter + timedelta(days=60): "Boże Ciało",
        date(year, 8, 15): "Wniebowzięcie NMP",
        date(year, 11, 1): "Wszystkich Świętych",
        date(year, 11, 11): "Święto Niepodległości",
        date(year, 12, 24): "Wigilia Bożego Narodzenia",
        date(year, 12, 25): "Boże Narodzenie",
        date(year, 12, 26): "Drugi dzień Bożego Narodzenia",
    }
    return result


def default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "schedule_enabled": False,
        "week": [
            {"weekday": d, "enabled": d != 7, "start_local": None, "end_local": None}
            for d in range(1, 8)
        ],
        "overrides": [],
    }


def _time(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    h, m = value[:2], value[3:]
    return h.isascii() and m.isascii() and h.isdecimal() and m.isdecimal() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59


def validate_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"enabled", "schedule_enabled", "week", "overrides"}:
        raise ValueError("autostart config requires enabled, schedule_enabled, week, overrides")
    if type(value["enabled"]) is not bool or type(value["schedule_enabled"]) is not bool:
        raise ValueError("autostart switches must be boolean")

    raw_week = value["week"]
    if not isinstance(raw_week, list) or len(raw_week) != 7:
        raise ValueError("week must include exactly seven weekdays")
    weekdays: dict[int, dict[str, Any]] = {}
    for row in raw_week:
        if not isinstance(row, Mapping) or set(row) != {"weekday", "enabled", "start_local", "end_local"}:
            raise ValueError("invalid weekday configuration")
        weekday = row["weekday"]
        if type(weekday) is not int or not 1 <= weekday <= 7 or weekday in weekdays:
            raise ValueError("weekdays must be unique ISO numbers 1..7")
        if type(row["enabled"]) is not bool:
            raise ValueError("weekday enabled must be boolean")
        start, end = row["start_local"], row["end_local"]
        if (start is None) != (end is None):
            raise ValueError("set both start and end time, or leave both empty")
        if start is not None:
            if not _time(start) or not _time(end) or start >= end:
                raise ValueError("weekday times must be HH:MM with start before end, within one day")
        weekdays[weekday] = {
            "weekday": weekday, "enabled": row["enabled"],
            "start_local": start, "end_local": end,
        }
    if set(weekdays) != set(range(1, 8)):
        raise ValueError("all seven weekdays required")

    overrides = value["overrides"]
    if not isinstance(overrides, list) or len(overrides) > MAX_OVERRIDES:
        raise ValueError(f"overrides must be a list of at most {MAX_OVERRIDES} dates")
    selected: dict[str, bool] = {}
    for item in overrides:
        if not isinstance(item, Mapping) or set(item) != {"date", "enabled"}:
            raise ValueError("date override requires date and enabled")
        value_date, enabled = item["date"], item["enabled"]
        if not isinstance(value_date, str) or type(enabled) is not bool:
            raise ValueError("date override requires YYYY-MM-DD and boolean")
        try:
            parsed = date.fromisoformat(value_date)
        except ValueError as exc:
            raise ValueError("date override must be a valid YYYY-MM-DD") from exc
        if parsed.isoformat() != value_date or not MIN_YEAR <= parsed.year <= MAX_YEAR or value_date in selected:
            raise ValueError("invalid, duplicate or out-of-range date override")
        selected[value_date] = enabled
    return {
        "enabled": value["enabled"], "schedule_enabled": value["schedule_enabled"],
        "week": [weekdays[d] for d in range(1, 8)],
        "overrides": [{"date": d, "enabled": selected[d]} for d in sorted(selected)],
    }


def year_days(config: Mapping[str, Any], year: int) -> list[dict[str, Any]]:
    if type(year) is not int or not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("year outside 2025..2100")
    holidays = polish_holidays(year)
    overrides = {item["date"]: item["enabled"] for item in config["overrides"]}
    week = {day["weekday"]: day for day in config["week"]}
    first = date(year, 1, 1)
    days = []
    for offset in range(366 if calendar.isleap(year) else 365):
        current = first + timedelta(days=offset)
        weekday = current.isoweekday()
        key = current.isoformat()
        holiday = holidays.get(current)
        if key in overrides:
            enabled, source = overrides[key], "override"
        elif holiday:
            enabled, source = False, "holiday"
        elif weekday == 7:
            enabled, source = False, "sunday"
        else:
            enabled, source = week[weekday]["enabled"], "weekly"
        days.append({
            "date": key, "weekday": weekday, "enabled": enabled,
            "source": source, "holiday": holiday,
            "start_local": week[weekday]["start_local"],
            "end_local": week[weekday]["end_local"],
        })
    return days
