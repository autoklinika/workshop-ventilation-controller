from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


SCHEDULE_TIMEZONE = "Europe/Warsaw"
MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY


class ScheduleExpectation(StrEnum):
    UNKNOWN = "UNKNOWN"
    OCCUPIED_EXPECTED = "OCCUPIED_EXPECTED"
    UNOCCUPIED_EXPECTED = "UNOCCUPIED_EXPECTED"


def parse_local_time(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("Local schedule time must be HH:MM text")
    parts = value.split(":")
    if len(parts) != 2 or any(len(part) != 2 or not part.isdigit() for part in parts):
        raise ValueError("Local schedule time must use HH:MM format")
    hour, minute = (int(part) for part in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Local schedule time is outside 00:00..23:59")
    return hour * 60 + minute


def format_local_time(minutes: int) -> str:
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes < MINUTES_PER_DAY:
        raise ValueError("Schedule minute must be in range 0..1439")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class ScheduleWindow:
    zone: str
    weekday: int
    start_minute: int
    end_minute: int
    expectation: ScheduleExpectation = ScheduleExpectation.OCCUPIED_EXPECTED
    enabled: bool = True
    label: str = ""
    window_id: int | None = None

    def __post_init__(self) -> None:
        zone = self.zone.strip() if isinstance(self.zone, str) else ""
        if not zone or len(zone) > 64:
            raise ValueError("Schedule zone must be non-empty and at most 64 characters")
        if zone != self.zone:
            raise ValueError("Schedule zone must not contain surrounding whitespace")
        if isinstance(self.weekday, bool) or not isinstance(self.weekday, int) or not 1 <= self.weekday <= 7:
            raise ValueError("Schedule weekday must use ISO range 1..7 (Monday..Sunday)")
        for field_name, value in (("start_minute", self.start_minute), ("end_minute", self.end_minute)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < MINUTES_PER_DAY:
                raise ValueError(f"{field_name} must be in range 0..1439")
        if self.start_minute == self.end_minute:
            raise ValueError("Schedule window start and end must differ")
        if self.expectation == ScheduleExpectation.UNKNOWN:
            raise ValueError("UNKNOWN cannot be stored as a schedule window expectation")
        if not isinstance(self.enabled, bool):
            raise ValueError("Schedule enabled flag must be boolean")
        if not isinstance(self.label, str) or len(self.label) > 80:
            raise ValueError("Schedule label must be text up to 80 characters")
        if self.window_id is not None and (
            isinstance(self.window_id, bool)
            or not isinstance(self.window_id, int)
            or self.window_id < 1
        ):
            raise ValueError("Schedule window_id must be a positive integer or null")

    @classmethod
    def from_payload(cls, zone: str, payload: Mapping[str, Any]) -> "ScheduleWindow":
        if not isinstance(payload, Mapping):
            raise ValueError("Each schedule window must be an object")
        try:
            weekday = payload["weekday"]
            start_local = payload["start_local"]
            end_local = payload["end_local"]
        except KeyError as exc:
            raise ValueError(f"Missing schedule field: {exc.args[0]}") from exc
        expectation_raw = payload.get("expectation", ScheduleExpectation.OCCUPIED_EXPECTED.value)
        try:
            expectation = ScheduleExpectation(str(expectation_raw))
        except ValueError as exc:
            raise ValueError(f"Unsupported schedule expectation: {expectation_raw}") from exc
        return cls(
            zone=zone,
            weekday=weekday,
            start_minute=parse_local_time(start_local),
            end_minute=parse_local_time(end_local),
            expectation=expectation,
            enabled=payload.get("enabled", True),
            label=payload.get("label", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "zone": self.zone,
            "weekday": self.weekday,
            "start_local": format_local_time(self.start_minute),
            "end_local": format_local_time(self.end_minute),
            "expectation": self.expectation.value,
            "enabled": self.enabled,
            "label": self.label,
        }

    def matches(self, local_dt: datetime) -> bool:
        if not self.enabled:
            return False
        minute = local_dt.hour * 60 + local_dt.minute
        weekday = local_dt.isoweekday()
        if self.end_minute > self.start_minute:
            return (
                weekday == self.weekday
                and self.start_minute <= minute < self.end_minute
            )
        next_weekday = 1 if self.weekday == 7 else self.weekday + 1
        return (
            weekday == self.weekday and minute >= self.start_minute
        ) or (
            weekday == next_weekday and minute < self.end_minute
        )

    def week_segments(self) -> tuple[tuple[int, int], ...]:
        if not self.enabled:
            return ()
        start = (self.weekday - 1) * MINUTES_PER_DAY + self.start_minute
        end = (self.weekday - 1) * MINUTES_PER_DAY + self.end_minute
        if self.end_minute <= self.start_minute:
            end += MINUTES_PER_DAY
        if end <= MINUTES_PER_WEEK:
            return ((start, end),)
        return ((start, MINUTES_PER_WEEK), (0, end - MINUTES_PER_WEEK))


@dataclass(frozen=True)
class ZoneScheduleState:
    zone: str
    expectation: ScheduleExpectation
    matched_window_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "expectation": self.expectation.value,
            "matched_window_id": self.matched_window_id,
        }


@dataclass(frozen=True)
class ScheduleState:
    available: bool
    timezone: str
    evaluated_at_utc: str
    local_time: str
    zones: tuple[ZoneScheduleState, ...]
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "timezone": self.timezone,
            "evaluated_at_utc": self.evaluated_at_utc,
            "local_time": self.local_time,
            "zones": [zone.to_dict() for zone in self.zones],
            "last_error": self.last_error,
        }


def validate_windows(windows: Sequence[ScheduleWindow]) -> None:
    by_zone: dict[str, list[ScheduleWindow]] = {}
    for window in windows:
        by_zone.setdefault(window.zone, []).append(window)
    for zone, zone_windows in by_zone.items():
        segments: list[tuple[int, int, int]] = []
        for index, window in enumerate(zone_windows):
            for start, end in window.week_segments():
                segments.append((start, end, index))
        segments.sort()
        for position, (start, end, index) in enumerate(segments):
            for other_start, other_end, other_index in segments[position + 1 :]:
                if other_start >= end:
                    break
                if index != other_index and start < other_end and other_start < end:
                    raise ValueError(f"Overlapping enabled schedule windows for zone {zone}")


def unavailable_schedule_state(
    zones: Sequence[str],
    *,
    error: str,
    now_utc: datetime | None = None,
    timezone_name: str = SCHEDULE_TIMEZONE,
) -> ScheduleState:
    now = now_utc or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(timezone_name))
    return ScheduleState(
        available=False,
        timezone=timezone_name,
        evaluated_at_utc=now.isoformat(),
        local_time=local.isoformat(),
        zones=tuple(
            ZoneScheduleState(zone=zone, expectation=ScheduleExpectation.UNKNOWN)
            for zone in zones
        ),
        last_error=error,
    )


def evaluate_schedule(
    windows: Sequence[ScheduleWindow],
    zones: Sequence[str],
    *,
    now_utc: datetime | None = None,
    timezone_name: str = SCHEDULE_TIMEZONE,
) -> ScheduleState:
    validate_windows(windows)
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Schedule evaluation requires timezone-aware UTC time")
    local = now.astimezone(ZoneInfo(timezone_name))
    states: list[ZoneScheduleState] = []
    for zone in zones:
        matching = [window for window in windows if window.zone == zone and window.matches(local)]
        if len(matching) > 1:
            raise ValueError(f"Multiple schedule windows match zone {zone}")
        if matching:
            states.append(
                ZoneScheduleState(
                    zone=zone,
                    expectation=matching[0].expectation,
                    matched_window_id=matching[0].window_id,
                )
            )
        else:
            states.append(
                ZoneScheduleState(
                    zone=zone,
                    expectation=ScheduleExpectation.UNOCCUPIED_EXPECTED,
                )
            )
    return ScheduleState(
        available=True,
        timezone=timezone_name,
        evaluated_at_utc=now.isoformat(),
        local_time=local.isoformat(),
        zones=tuple(states),
    )
