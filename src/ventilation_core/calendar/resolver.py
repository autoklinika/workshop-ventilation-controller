from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .model import (
    CalendarConfig,
    CalendarMode,
    CalendarPhase,
    CalendarResolution,
    CalendarRule,
)


@dataclass(frozen=True)
class _Period:
    rule: CalendarRule
    profile_id: str
    mode: CalendarMode
    pre_start: datetime
    active_start: datetime
    active_end: datetime
    purge_end: datetime


def _local_at(local_date: date, minute: int, tz: ZoneInfo) -> datetime:
    return datetime.combine(local_date, time(minute // 60, minute % 60), tzinfo=tz)


def _selected_rules(config: CalendarConfig, local_date: date) -> tuple[CalendarRule, ...]:
    matching = [rule for rule in config.rules if rule.matches_date(local_date)]
    if not matching:
        return ()
    priority = max(rule.priority for rule in matching)
    selected = sorted(
        (rule for rule in matching if rule.priority == priority),
        key=lambda rule: (rule.start_minute is None, rule.start_minute or -1, rule.rule_id),
    )
    _validate_same_day_rules(selected, local_date)
    return tuple(selected)


def _validate_same_day_rules(rules: list[CalendarRule], local_date: date) -> None:
    if not rules:
        return
    full_day = [rule for rule in rules if rule.full_day]
    if full_day and len(rules) > 1:
        raise ValueError(f"full-day calendar rule conflicts with another rule on {local_date}")
    windows: list[tuple[int, int, str]] = []
    for rule in rules:
        if rule.start_minute is None or rule.end_minute is None:
            continue
        start = rule.start_minute
        end = rule.end_minute
        if end <= start:
            end += 24 * 60
        windows.append((start, end, rule.rule_id))
    windows.sort()
    for index, (start, end, rule_id) in enumerate(windows):
        for other_start, other_end, other_id in windows[index + 1 :]:
            if other_start >= end:
                break
            if start < other_end and other_start < end:
                raise ValueError(f"overlapping calendar rules {rule_id} and {other_id} on {local_date}")


def _periods_for_date(config: CalendarConfig, local_date: date, tz: ZoneInfo) -> tuple[_Period, ...]:
    periods: list[_Period] = []
    for rule in _selected_rules(config, local_date):
        profile = config.profile(rule.profile_id)
        if rule.full_day:
            if profile.mode in {CalendarMode.OFF, CalendarMode.STANDBY}:
                continue
            active_start = datetime.combine(local_date, time.min, tzinfo=tz)
            active_end = active_start + timedelta(days=1)
        else:
            assert rule.start_minute is not None and rule.end_minute is not None
            active_start = _local_at(local_date, rule.start_minute, tz)
            end_date = local_date if rule.end_minute > rule.start_minute else local_date + timedelta(days=1)
            active_end = _local_at(end_date, rule.end_minute, tz)
        pre_start = active_start - timedelta(minutes=profile.preventilation_minutes)
        purge_end = active_end + timedelta(minutes=profile.purge_minutes)
        periods.append(
            _Period(
                rule=rule,
                profile_id=profile.profile_id,
                mode=profile.mode,
                pre_start=pre_start,
                active_start=active_start,
                active_end=active_end,
                purge_end=purge_end,
            )
        )
    return tuple(periods)


def _full_day_context(config: CalendarConfig, local_date: date) -> tuple[CalendarRule, CalendarMode] | None:
    selected = _selected_rules(config, local_date)
    if len(selected) == 1 and selected[0].full_day:
        profile = config.profile(selected[0].profile_id)
        return selected[0], profile.mode
    return None


def resolve_calendar(
    config: CalendarConfig,
    *,
    now_utc: datetime | None = None,
    search_days: int = 370,
) -> CalendarResolution:
    if search_days < 1:
        raise ValueError("search_days must be positive")
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("calendar resolution requires timezone-aware datetime")
    now = now.astimezone(timezone.utc)
    tz = ZoneInfo(config.timezone)
    local_now = now.astimezone(tz)

    candidate_periods: list[_Period] = []
    for offset in (-1, 0):
        candidate_periods.extend(_periods_for_date(config, local_now.date() + timedelta(days=offset), tz))

    current: _Period | None = None
    phase = CalendarPhase.INACTIVE
    next_transition: datetime | None = None
    next_reason: str | None = None
    for period in sorted(candidate_periods, key=lambda item: item.pre_start):
        if period.pre_start <= local_now < period.active_start:
            current, phase = period, CalendarPhase.PREVENTILATION
            next_transition, next_reason = period.active_start, "START_ACTIVE"
            break
        if period.active_start <= local_now < period.active_end:
            current, phase = period, CalendarPhase.ACTIVE
            next_transition, next_reason = period.active_end, "START_PURGE"
            break
        if period.active_end <= local_now < period.purge_end:
            current, phase = period, CalendarPhase.PURGE
            next_transition, next_reason = period.purge_end, "END_PURGE"
            break

    next_period: _Period | None = None
    start_date = local_now.date()
    for day_offset in range(0, search_days + 1):
        for period in _periods_for_date(config, start_date + timedelta(days=day_offset), tz):
            if period.pre_start > local_now:
                if next_period is None or period.pre_start < next_period.pre_start:
                    next_period = period
        if next_period is not None and day_offset > 1:
            break

    if current is None:
        full_day = _full_day_context(config, local_now.date())
        if full_day is not None:
            rule, mode = full_day
            effective_profile = rule.profile_id
            effective_mode = mode
            rule_id = rule.rule_id
            rule_source = rule.kind
        else:
            effective_profile = None
            effective_mode = CalendarMode.OFF
            rule_id = None
            rule_source = None
        if next_period is not None:
            next_transition = next_period.pre_start
            next_reason = "START_PREVENTILATION"
        current_start = None
        current_end = None
    else:
        effective_profile = current.profile_id
        effective_mode = current.mode
        rule_id = current.rule.rule_id
        rule_source = current.rule.kind
        current_start = current.pre_start.isoformat()
        current_end = current.purge_end.isoformat()

    return CalendarResolution(
        available=True,
        timezone=config.timezone,
        evaluated_at_utc=now.isoformat(),
        local_time=local_now.isoformat(),
        phase=phase,
        effective_profile=effective_profile,
        effective_mode=effective_mode,
        rule_id=rule_id,
        rule_source=rule_source,
        current_period_start=current_start,
        current_period_end=current_end,
        next_transition=None if next_transition is None else next_transition.isoformat(),
        next_transition_reason=next_reason,
        next_active_period=None if next_period is None else next_period.active_start.isoformat(),
        next_wake=None if next_period is None else next_period.pre_start.isoformat(),
    )
