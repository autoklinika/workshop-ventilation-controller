from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .model import (
    MINUTES_PER_DAY,
    CalendarConfig,
    CalendarMode,
    CalendarPhase,
    CalendarProfile,
    CalendarResolution,
    CalendarRule,
    CalendarRuleKind,
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
            end += MINUTES_PER_DAY
        windows.append((start, end, rule.rule_id))
    windows.sort()
    for index, (start, end, rule_id) in enumerate(windows):
        for other_start, other_end, other_id in windows[index + 1 :]:
            if other_start >= end:
                break
            if start < other_end and other_start < end:
                raise ValueError(f"overlapping calendar rules {rule_id} and {other_id} on {local_date}")


def _rule_effective_bounds(rule: CalendarRule, profile: CalendarProfile) -> tuple[int, int]:
    """Return the complete PREVENTILATION..PURGE interval relative to rule date.

    Full-day OFF/STANDBY rules are closed contexts rather than active periods, so
    profile pre/purge values have no runtime effect and are intentionally ignored.
    """

    if rule.full_day:
        if profile.mode in {CalendarMode.OFF, CalendarMode.STANDBY}:
            return 0, MINUTES_PER_DAY
        active_start = 0
        active_end = MINUTES_PER_DAY
    else:
        assert rule.start_minute is not None and rule.end_minute is not None
        active_start = rule.start_minute
        active_end = rule.end_minute
        if active_end <= active_start:
            active_end += MINUTES_PER_DAY
    return (
        active_start - profile.preventilation_minutes,
        active_end + profile.purge_minutes,
    )


def _selectors_can_align(
    first: CalendarRule,
    second: CalendarRule,
    start_date_offset_days: int,
) -> bool:
    """Return whether two same-priority rules can start on dates with this offset."""

    if not first.enabled or not second.enabled or first.kind != second.kind:
        return False

    kind = first.kind
    delta = timedelta(days=start_date_offset_days)
    if kind == CalendarRuleKind.DEFAULT:
        return True
    if kind == CalendarRuleKind.WEEKLY:
        second_days = set(second.weekdays)
        return any(
            ((weekday - 1 + start_date_offset_days) % 7) + 1 in second_days
            for weekday in first.weekdays
        )
    if kind == CalendarRuleKind.SEASON:
        # One leap year covers every month boundary, including February 29.
        representative = date(2028, 1, 1)
        for day_index in range(366):
            first_date = representative + timedelta(days=day_index)
            second_date = first_date + delta
            if first_date.month in first.months and second_date.month in second.months:
                return True
        return False
    if kind == CalendarRuleKind.DATE_RANGE:
        assert first.start_date is not None and first.end_date is not None
        assert second.start_date is not None and second.end_date is not None
        shifted_second_start = second.start_date - delta
        shifted_second_end = second.end_date - delta
        return max(first.start_date, shifted_second_start) <= min(
            first.end_date,
            shifted_second_end,
        )
    if kind == CalendarRuleKind.DATE_EXCEPTION:
        assert first.start_date is not None and second.start_date is not None
        return first.start_date + delta == second.start_date
    return False


def validate_calendar_configuration(config: CalendarConfig) -> None:
    """Reject latent same-priority conflicts before configuration persistence.

    Runtime precedence is date-kind based. Rules with different priorities may
    intentionally cover the same dates, but rules at the same priority must not
    create ambiguous effective periods. Validation includes adjacent start dates,
    overnight windows and PREVENTILATION/PURGE extensions, so a conflict cannot
    remain dormant until a future date.
    """

    enabled = [rule for rule in config.rules if rule.enabled]
    profiles = {profile.profile_id: profile for profile in config.profiles}

    for first_index, first in enumerate(enabled):
        first_profile = profiles[first.profile_id]
        first_start, first_end = _rule_effective_bounds(first, first_profile)
        for second_index in range(first_index, len(enabled)):
            second = enabled[second_index]
            if second.priority != first.priority:
                continue
            second_profile = profiles[second.profile_id]
            second_start, second_end = _rule_effective_bounds(second, second_profile)

            # A timed overnight window may end almost two days after its rule
            # date and PURGE may extend another full day. PREVENTILATION may
            # begin one day before the other rule date, so start dates up to
            # three days apart must be checked. Four days can only touch, not
            # overlap, at the configured maxima.
            for day_offset in range(-3, 4):
                if first_index == second_index and day_offset == 0:
                    continue
                if not _selectors_can_align(first, second, day_offset):
                    continue
                shifted_second_start = second_start + day_offset * MINUTES_PER_DAY
                shifted_second_end = second_end + day_offset * MINUTES_PER_DAY
                if first_start < shifted_second_end and shifted_second_start < first_end:
                    raise ValueError(
                        "overlapping calendar effective periods: "
                        f"{first.rule_id} and {second.rule_id} "
                        f"(start-date offset {day_offset:+d}d)"
                    )


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

    # A configured period may begin PREVENTILATION on the previous local day,
    # and an overnight period with a long PURGE may remain current for up to two
    # days after its rule date. Include exactly that bounded start-date envelope.
    candidate_periods: list[_Period] = []
    for offset in (-2, -1, 0, 1):
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
