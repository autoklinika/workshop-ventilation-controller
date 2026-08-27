from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Mapping, Sequence


DEFAULT_TIMEZONE = "Europe/Warsaw"
MINUTES_PER_DAY = 24 * 60


class CalendarMode(StrEnum):
    AUTO = "AUTO"
    FIXED = "FIXED"
    STANDBY = "STANDBY"
    OFF = "OFF"


class CalendarRuleKind(StrEnum):
    DEFAULT = "DEFAULT"
    WEEKLY = "WEEKLY"
    SEASON = "SEASON"
    DATE_RANGE = "DATE_RANGE"
    DATE_EXCEPTION = "DATE_EXCEPTION"


class CalendarPhase(StrEnum):
    INACTIVE = "INACTIVE"
    PREVENTILATION = "PREVENTILATION"
    ACTIVE = "ACTIVE"
    PURGE = "PURGE"


RULE_PRIORITY: dict[CalendarRuleKind, int] = {
    CalendarRuleKind.DEFAULT: 10,
    CalendarRuleKind.WEEKLY: 20,
    CalendarRuleKind.SEASON: 30,
    CalendarRuleKind.DATE_RANGE: 40,
    CalendarRuleKind.DATE_EXCEPTION: 50,
}


def parse_hhmm(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("time must be HH:MM text")
    parts = value.split(":")
    if len(parts) != 2 or any(len(part) != 2 or not part.isdigit() for part in parts):
        raise ValueError("time must use HH:MM format")
    hour, minute = (int(part) for part in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time is outside 00:00..23:59")
    return hour * 60 + minute


def format_hhmm(minutes: int) -> str:
    if (
        isinstance(minutes, bool)
        or not isinstance(minutes, int)
        or not 0 <= minutes < MINUTES_PER_DAY
    ):
        raise ValueError("minute must be in range 0..1439")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_date(value: str | date | None, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _enum(enum_type, value: Any, field: str):
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {field}: {value}") from exc


def _integer_sequence(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list of integers")
    result = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in result):
        raise ValueError(f"{field} must contain integers without type coercion")
    return result


@dataclass(frozen=True)
class CalendarProfile:
    profile_id: str
    mode: CalendarMode
    preventilation_minutes: int = 0
    purge_minutes: int = 0
    minimum_supply_pct: float | None = None
    minimum_extract_pct: float | None = None
    fixed_supply_pct: float | None = None
    fixed_extract_pct: float | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or self.profile_id.strip() != self.profile_id
            or len(self.profile_id) > 64
        ):
            raise ValueError("profile_id must be non-empty text up to 64 characters")
        if not isinstance(self.mode, CalendarMode):
            raise ValueError("mode must be a CalendarMode")
        for name, value in (
            ("preventilation_minutes", self.preventilation_minutes),
            ("purge_minutes", self.purge_minutes),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 24 * 60
            ):
                raise ValueError(f"{name} must be an integer in range 0..1440")
        for name, value in (
            ("minimum_supply_pct", self.minimum_supply_pct),
            ("minimum_extract_pct", self.minimum_extract_pct),
            ("fixed_supply_pct", self.fixed_supply_pct),
            ("fixed_extract_pct", self.fixed_extract_pct),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= float(value) <= 100
            ):
                raise ValueError(f"{name} must be null or 0..100")
        if self.mode == CalendarMode.FIXED and (
            self.fixed_supply_pct is None or self.fixed_extract_pct is None
        ):
            raise ValueError("FIXED profile requires fixed_supply_pct and fixed_extract_pct")
        if not isinstance(self.label, str) or len(self.label) > 120:
            raise ValueError("profile label must be text up to 120 characters")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalendarProfile":
        if not isinstance(payload, Mapping):
            raise ValueError("profile must be an object")
        return cls(
            profile_id=payload["profile_id"],
            mode=_enum(CalendarMode, payload["mode"], "calendar mode"),
            preventilation_minutes=payload.get("preventilation_minutes", 0),
            purge_minutes=payload.get("purge_minutes", 0),
            minimum_supply_pct=payload.get("minimum_supply_pct"),
            minimum_extract_pct=payload.get("minimum_extract_pct"),
            fixed_supply_pct=payload.get("fixed_supply_pct"),
            fixed_extract_pct=payload.get("fixed_extract_pct"),
            label=payload.get("label", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "mode": self.mode.value,
            "preventilation_minutes": self.preventilation_minutes,
            "purge_minutes": self.purge_minutes,
            "minimum_supply_pct": self.minimum_supply_pct,
            "minimum_extract_pct": self.minimum_extract_pct,
            "fixed_supply_pct": self.fixed_supply_pct,
            "fixed_extract_pct": self.fixed_extract_pct,
            "label": self.label,
        }


@dataclass(frozen=True)
class CalendarRule:
    rule_id: str
    kind: CalendarRuleKind
    profile_id: str
    weekdays: tuple[int, ...] = ()
    months: tuple[int, ...] = ()
    start_date: date | None = None
    end_date: date | None = None
    start_minute: int | None = None
    end_minute: int | None = None
    enabled: bool = True
    label: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rule_id, str)
            or not self.rule_id
            or self.rule_id.strip() != self.rule_id
            or len(self.rule_id) > 64
        ):
            raise ValueError("rule_id must be non-empty text up to 64 characters")
        if not isinstance(self.kind, CalendarRuleKind):
            raise ValueError("kind must be a CalendarRuleKind")
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or self.profile_id.strip() != self.profile_id
        ):
            raise ValueError("profile_id must be non-empty text")
        if len(set(self.weekdays)) != len(self.weekdays) or any(
            isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 7
            for v in self.weekdays
        ):
            raise ValueError("weekdays must use unique ISO values 1..7")
        if len(set(self.months)) != len(self.months) or any(
            isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 12
            for v in self.months
        ):
            raise ValueError("months must use unique values 1..12")
        if (self.start_minute is None) != (self.end_minute is None):
            raise ValueError("start_minute and end_minute must both be set or both be null")
        for name, value in (("start_minute", self.start_minute), ("end_minute", self.end_minute)):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value < MINUTES_PER_DAY
            ):
                raise ValueError(f"{name} must be null or in range 0..1439")
        if self.start_minute is not None and self.start_minute == self.end_minute:
            raise ValueError("calendar window start and end must differ")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not precede start_date")
        if self.kind == CalendarRuleKind.WEEKLY and not self.weekdays:
            raise ValueError("WEEKLY rule requires weekdays")
        if self.kind == CalendarRuleKind.SEASON and not self.months:
            raise ValueError("SEASON rule requires months")
        if self.kind == CalendarRuleKind.DATE_RANGE and (
            self.start_date is None or self.end_date is None
        ):
            raise ValueError("DATE_RANGE rule requires start_date and end_date")
        if self.kind == CalendarRuleKind.DATE_EXCEPTION and (
            self.start_date is None or self.end_date != self.start_date
        ):
            raise ValueError("DATE_EXCEPTION rule requires one exact date")
        if self.kind == CalendarRuleKind.DEFAULT and (
            self.weekdays
            or self.months
            or self.start_date is not None
            or self.end_date is not None
        ):
            raise ValueError("DEFAULT rule cannot contain date selectors")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be boolean")
        if not isinstance(self.label, str) or len(self.label) > 120:
            raise ValueError("rule label must be text up to 120 characters")

    @property
    def priority(self) -> int:
        return RULE_PRIORITY[self.kind]

    @property
    def full_day(self) -> bool:
        return self.start_minute is None

    def matches_date(self, local_date: date) -> bool:
        if not self.enabled:
            return False
        if self.kind == CalendarRuleKind.DEFAULT:
            return True
        if self.kind == CalendarRuleKind.WEEKLY:
            return local_date.isoweekday() in self.weekdays
        if self.kind == CalendarRuleKind.SEASON:
            return local_date.month in self.months
        if self.kind == CalendarRuleKind.DATE_RANGE:
            return bool(self.start_date <= local_date <= self.end_date)  # type: ignore[operator]
        if self.kind == CalendarRuleKind.DATE_EXCEPTION:
            return local_date == self.start_date
        return False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalendarRule":
        if not isinstance(payload, Mapping):
            raise ValueError("rule must be an object")
        start_local = payload.get("start_local")
        end_local = payload.get("end_local")
        return cls(
            rule_id=payload["rule_id"],
            kind=_enum(CalendarRuleKind, payload["kind"], "calendar rule kind"),
            profile_id=payload["profile_id"],
            weekdays=_integer_sequence(payload.get("weekdays", ()), "weekdays"),
            months=_integer_sequence(payload.get("months", ()), "months"),
            start_date=_parse_date(payload.get("start_date"), "start_date"),
            end_date=_parse_date(payload.get("end_date"), "end_date"),
            start_minute=None if start_local is None else parse_hhmm(start_local),
            end_minute=None if end_local is None else parse_hhmm(end_local),
            enabled=payload.get("enabled", True),
            label=payload.get("label", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "kind": self.kind.value,
            "profile_id": self.profile_id,
            "weekdays": list(self.weekdays),
            "months": list(self.months),
            "start_date": None if self.start_date is None else self.start_date.isoformat(),
            "end_date": None if self.end_date is None else self.end_date.isoformat(),
            "start_local": None if self.start_minute is None else format_hhmm(self.start_minute),
            "end_local": None if self.end_minute is None else format_hhmm(self.end_minute),
            "enabled": self.enabled,
            "label": self.label,
        }


@dataclass(frozen=True)
class CalendarConfig:
    timezone: str
    profiles: tuple[CalendarProfile, ...]
    rules: tuple[CalendarRule, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.timezone, str) or not self.timezone or len(self.timezone) > 64:
            raise ValueError("timezone must be non-empty text")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != 1
        ):
            raise ValueError("unsupported calendar schema_version")
        profile_ids = [p.profile_id for p in self.profiles]
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("duplicate calendar profile_id")
        rule_ids = [r.rule_id for r in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("duplicate calendar rule_id")
        known = set(profile_ids)
        for rule in self.rules:
            if rule.profile_id not in known:
                raise ValueError(
                    f"calendar rule {rule.rule_id} references unknown profile {rule.profile_id}"
                )
        if sum(
            1
            for rule in self.rules
            if rule.kind == CalendarRuleKind.DEFAULT and rule.enabled
        ) > 1:
            raise ValueError("at most one enabled DEFAULT rule is allowed")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalendarConfig":
        if not isinstance(payload, Mapping):
            raise ValueError("calendar config must be an object")
        profiles = payload.get("profiles", [])
        rules = payload.get("rules", [])
        if not isinstance(profiles, Sequence) or isinstance(profiles, (str, bytes, bytearray)):
            raise ValueError("profiles must be a list")
        if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes, bytearray)):
            raise ValueError("rules must be a list")
        return cls(
            timezone=payload.get("timezone", DEFAULT_TIMEZONE),
            profiles=tuple(CalendarProfile.from_dict(item) for item in profiles),
            rules=tuple(CalendarRule.from_dict(item) for item in rules),
            schema_version=payload.get("schema_version", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timezone": self.timezone,
            "profiles": [p.to_dict() for p in self.profiles],
            "rules": [r.to_dict() for r in self.rules],
        }

    def profile(self, profile_id: str) -> CalendarProfile:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        raise KeyError(profile_id)


@dataclass(frozen=True)
class CalendarResolution:
    available: bool
    timezone: str
    evaluated_at_utc: str
    local_time: str
    phase: CalendarPhase
    effective_profile: str | None = None
    effective_mode: CalendarMode | None = None
    rule_id: str | None = None
    rule_source: CalendarRuleKind | None = None
    current_period_start: str | None = None
    current_period_end: str | None = None
    next_transition: str | None = None
    next_transition_reason: str | None = None
    next_active_period: str | None = None
    next_wake: str | None = None
    schedule_supply_pct: float | None = None
    schedule_extract_pct: float | None = None
    schedule_request_source: str | None = None
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "timezone": self.timezone,
            "evaluated_at_utc": self.evaluated_at_utc,
            "local_time": self.local_time,
            "phase": self.phase.value,
            "effective_profile": self.effective_profile,
            "effective_mode": None if self.effective_mode is None else self.effective_mode.value,
            "rule_id": self.rule_id,
            "rule_source": None if self.rule_source is None else self.rule_source.value,
            "current_period_start": self.current_period_start,
            "current_period_end": self.current_period_end,
            "next_transition": self.next_transition,
            "next_transition_reason": self.next_transition_reason,
            "next_active_period": self.next_active_period,
            "next_wake": self.next_wake,
            "schedule_supply_pct": self.schedule_supply_pct,
            "schedule_extract_pct": self.schedule_extract_pct,
            "schedule_request_source": self.schedule_request_source,
            "last_error": self.last_error,
        }


def unavailable_resolution(
    *,
    now_utc: datetime,
    timezone_name: str,
    error: str,
) -> CalendarResolution:
    return CalendarResolution(
        available=False,
        timezone=timezone_name,
        evaluated_at_utc=now_utc.isoformat(),
        local_time=now_utc.isoformat(),
        phase=CalendarPhase.INACTIVE,
        last_error=error,
    )
