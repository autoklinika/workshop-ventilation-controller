from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ventilation_core.calendar.engine import CalendarRuntime
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.infrastructure.rtc_wake import RtcWakeAlarm, RtcWakeArmError


RTC_WAKE_ARM_FAILED = "RTC_WAKE_ARM_FAILED"


@dataclass(frozen=True)
class PowerSchedulerState:
    scheduled_shutdown_enabled: bool
    shutdown_ready: bool
    next_shutdown_at: str | None
    next_wake_at_local: str | None
    next_wake_at_utc: str | None
    next_wake_reason: str | None
    rtc_alarm_armed: bool
    rtc_alarm_verified: bool
    rtc_alarm_value: int | None
    shutdown_inhibited_reason: str | None
    alert_code: str | None
    last_error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "scheduled_shutdown_enabled": self.scheduled_shutdown_enabled,
            "shutdown_ready": self.shutdown_ready,
            "next_shutdown_at": self.next_shutdown_at,
            "next_wake_at_local": self.next_wake_at_local,
            "next_wake_at_utc": self.next_wake_at_utc,
            "next_wake_reason": self.next_wake_reason,
            "rtc_alarm_armed": self.rtc_alarm_armed,
            "rtc_alarm_verified": self.rtc_alarm_verified,
            "rtc_alarm_value": self.rtc_alarm_value,
            "shutdown_inhibited_reason": self.shutdown_inhibited_reason,
            "alert_code": self.alert_code,
            "last_error": self.last_error,
        }


class HostPowerRequester(Protocol):
    def request_shutdown(self) -> None: ...


class PowerScheduler:
    """Calendar-driven scheduled shutdown coordinator.

    M4 deliberately does not invoke host power. It validates calendar intent and,
    when explicitly asked to prepare a scheduled shutdown, arms and verifies RTC.
    A later production stage may consume `shutdown_ready=True` and call the existing
    privileged host-power agent.
    """

    def __init__(
        self,
        calendar: CalendarRuntime,
        rtc: RtcWakeAlarm,
        *,
        enabled: bool = False,
        minimum_wake_lead_seconds: int = 120,
    ) -> None:
        if isinstance(minimum_wake_lead_seconds, bool) or not isinstance(
            minimum_wake_lead_seconds, int
        ):
            raise ValueError("minimum_wake_lead_seconds must be an integer")
        if minimum_wake_lead_seconds < 1:
            raise ValueError("minimum_wake_lead_seconds must be positive")
        self._calendar = calendar
        self._rtc = rtc
        self._enabled = bool(enabled)
        self._minimum_wake_lead_seconds = minimum_wake_lead_seconds

    @property
    def enabled(self) -> bool:
        return self._enabled

    def diagnostics(self, now_utc: datetime | None = None) -> PowerSchedulerState:
        now = _aware_utc(now_utc)
        resolution = self._calendar.resolve(now)
        return self._plan(resolution, now)

    def prepare_scheduled_shutdown(
        self,
        now_utc: datetime | None = None,
    ) -> PowerSchedulerState:
        now = _aware_utc(now_utc)
        resolution = self._calendar.resolve(now)
        planned = self._plan(resolution, now)
        if planned.shutdown_inhibited_reason is not None:
            return planned

        if resolution.phase != CalendarPhase.INACTIVE:
            return _replace_inhibited(planned, "calendar_not_inactive")
        if resolution.effective_mode not in {CalendarMode.STANDBY, CalendarMode.OFF}:
            return _replace_inhibited(planned, "calendar_mode_not_shutdown_eligible")
        if planned.next_wake_at_utc is None:
            return _replace_inhibited(planned, "next_wake_unavailable")

        wake_utc = datetime.fromisoformat(planned.next_wake_at_utc)
        try:
            armed = self._rtc.arm(
                wake_utc,
                minimum_lead_seconds=self._minimum_wake_lead_seconds,
            )
        except Exception as exc:
            return PowerSchedulerState(
                scheduled_shutdown_enabled=self._enabled,
                shutdown_ready=False,
                next_shutdown_at=planned.next_shutdown_at,
                next_wake_at_local=planned.next_wake_at_local,
                next_wake_at_utc=planned.next_wake_at_utc,
                next_wake_reason=planned.next_wake_reason,
                rtc_alarm_armed=False,
                rtc_alarm_verified=False,
                rtc_alarm_value=None,
                shutdown_inhibited_reason="rtc_wake_arm_failed",
                alert_code=RTC_WAKE_ARM_FAILED,
                last_error=str(exc),
            )

        return PowerSchedulerState(
            scheduled_shutdown_enabled=self._enabled,
            shutdown_ready=True,
            next_shutdown_at=planned.next_shutdown_at,
            next_wake_at_local=planned.next_wake_at_local,
            next_wake_at_utc=planned.next_wake_at_utc,
            next_wake_reason=planned.next_wake_reason,
            rtc_alarm_armed=True,
            rtc_alarm_verified=armed.verified,
            rtc_alarm_value=armed.verified_epoch,
            shutdown_inhibited_reason=None,
            alert_code=None,
            last_error="",
        )

    def _plan(self, resolution: CalendarResolution, now_utc: datetime) -> PowerSchedulerState:
        if not self._enabled:
            return PowerSchedulerState(
                scheduled_shutdown_enabled=False,
                shutdown_ready=False,
                next_shutdown_at=_candidate_shutdown_at(resolution, now_utc),
                next_wake_at_local=resolution.next_wake,
                next_wake_at_utc=_iso_to_utc(resolution.next_wake),
                next_wake_reason=_next_wake_reason(resolution),
                rtc_alarm_armed=False,
                rtc_alarm_verified=False,
                rtc_alarm_value=None,
                shutdown_inhibited_reason="scheduled_shutdown_disabled",
                alert_code=None,
            )

        if not resolution.available:
            return PowerSchedulerState(
                scheduled_shutdown_enabled=True,
                shutdown_ready=False,
                next_shutdown_at=None,
                next_wake_at_local=None,
                next_wake_at_utc=None,
                next_wake_reason=None,
                rtc_alarm_armed=False,
                rtc_alarm_verified=False,
                rtc_alarm_value=None,
                shutdown_inhibited_reason="calendar_unavailable",
                alert_code=None,
                last_error=resolution.last_error,
            )

        next_wake_utc = _iso_to_utc(resolution.next_wake)
        if resolution.next_wake is None or next_wake_utc is None:
            return PowerSchedulerState(
                scheduled_shutdown_enabled=True,
                shutdown_ready=False,
                next_shutdown_at=_candidate_shutdown_at(resolution, now_utc),
                next_wake_at_local=resolution.next_wake,
                next_wake_at_utc=None,
                next_wake_reason=_next_wake_reason(resolution),
                rtc_alarm_armed=False,
                rtc_alarm_verified=False,
                rtc_alarm_value=None,
                shutdown_inhibited_reason="next_wake_unavailable",
                alert_code=None,
            )

        wake_dt = datetime.fromisoformat(next_wake_utc)
        lead = int(wake_dt.timestamp()) - int(now_utc.timestamp())
        if lead < self._minimum_wake_lead_seconds:
            return PowerSchedulerState(
                scheduled_shutdown_enabled=True,
                shutdown_ready=False,
                next_shutdown_at=_candidate_shutdown_at(resolution, now_utc),
                next_wake_at_local=resolution.next_wake,
                next_wake_at_utc=next_wake_utc,
                next_wake_reason=_next_wake_reason(resolution),
                rtc_alarm_armed=False,
                rtc_alarm_verified=False,
                rtc_alarm_value=None,
                shutdown_inhibited_reason="next_wake_too_close",
                alert_code=None,
                last_error=(
                    f"next_wake lead={lead}s is below minimum "
                    f"{self._minimum_wake_lead_seconds}s"
                ),
            )

        return PowerSchedulerState(
            scheduled_shutdown_enabled=True,
            shutdown_ready=False,
            next_shutdown_at=_candidate_shutdown_at(resolution, now_utc),
            next_wake_at_local=resolution.next_wake,
            next_wake_at_utc=next_wake_utc,
            next_wake_reason=_next_wake_reason(resolution),
            rtc_alarm_armed=False,
            rtc_alarm_verified=False,
            rtc_alarm_value=None,
            shutdown_inhibited_reason=None,
            alert_code=None,
        )


def _aware_utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("power scheduler requires timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _iso_to_utc(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("calendar timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _candidate_shutdown_at(resolution: CalendarResolution, now_utc: datetime) -> str | None:
    if not resolution.available:
        return None
    if resolution.phase in {
        CalendarPhase.PREVENTILATION,
        CalendarPhase.ACTIVE,
        CalendarPhase.PURGE,
    }:
        return resolution.current_period_end
    if resolution.phase == CalendarPhase.INACTIVE:
        return now_utc.astimezone(timezone.utc).isoformat()
    return None


def _next_wake_reason(resolution: CalendarResolution) -> str | None:
    if resolution.next_wake is None:
        return None
    profile = resolution.effective_profile or "next_calendar_period"
    return f"{profile}/PREVENTILATION"


def _replace_inhibited(state: PowerSchedulerState, reason: str) -> PowerSchedulerState:
    return PowerSchedulerState(
        scheduled_shutdown_enabled=state.scheduled_shutdown_enabled,
        shutdown_ready=False,
        next_shutdown_at=state.next_shutdown_at,
        next_wake_at_local=state.next_wake_at_local,
        next_wake_at_utc=state.next_wake_at_utc,
        next_wake_reason=state.next_wake_reason,
        rtc_alarm_armed=False,
        rtc_alarm_verified=False,
        rtc_alarm_value=None,
        shutdown_inhibited_reason=reason,
        alert_code=None,
        last_error=state.last_error,
    )
