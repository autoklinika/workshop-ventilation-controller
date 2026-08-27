from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ventilation_core.calendar.engine import CalendarRuntime
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.infrastructure.rtc_wake import RtcWakeAlarm


RTC_WAKE_ARM_FAILED = "RTC_WAKE_ARM_FAILED"
HOST_POWER_REQUEST_FAILED = "HOST_POWER_REQUEST_FAILED"


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


@dataclass(frozen=True)
class ScheduledShutdownExecution:
    state: PowerSchedulerState
    host_power_requested: bool
    host_power_accepted: bool
    host_power_response: dict[str, object] | None
    alert_code: str | None
    last_error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.to_dict(),
            "host_power_requested": self.host_power_requested,
            "host_power_accepted": self.host_power_accepted,
            "host_power_response": self.host_power_response,
            "alert_code": self.alert_code,
            "last_error": self.last_error,
        }


class HostPowerRequester(Protocol):
    def request(self, action: str) -> dict[str, object]: ...


class PowerScheduler:
    """Calendar-driven scheduled shutdown coordinator.

    The coordinator is fail-safe: the host-power boundary is never called until
    the Calendar Engine explicitly resolves an inactive STANDBY/OFF period and
    the RTC wake alarm has been armed and read back exactly. If the host-power
    request is rejected or fails, the RTC alarm is cleared best-effort and the
    CM5 remains running.
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
        expected_epoch = int(wake_utc.timestamp())
        try:
            armed = self._rtc.arm(
                wake_utc,
                minimum_lead_seconds=self._minimum_wake_lead_seconds,
            )
            if armed.verified is not True or armed.verified_epoch != expected_epoch:
                raise RuntimeError(
                    "RTC wake verification mismatch: "
                    f"expected={expected_epoch}, verified={armed.verified_epoch}, "
                    f"flag={armed.verified!r}"
                )
        except Exception as exc:
            clear_error = self._best_effort_clear_rtc()
            error = str(exc)
            if clear_error:
                error = f"{error}; RTC cleanup failed: {clear_error}"
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
                last_error=error,
            )

        return PowerSchedulerState(
            scheduled_shutdown_enabled=self._enabled,
            shutdown_ready=True,
            next_shutdown_at=planned.next_shutdown_at,
            next_wake_at_local=planned.next_wake_at_local,
            next_wake_at_utc=planned.next_wake_at_utc,
            next_wake_reason=planned.next_wake_reason,
            rtc_alarm_armed=True,
            rtc_alarm_verified=True,
            rtc_alarm_value=armed.verified_epoch,
            shutdown_inhibited_reason=None,
            alert_code=None,
            last_error="",
        )

    def execute_scheduled_shutdown(
        self,
        host_power: HostPowerRequester,
        now_utc: datetime | None = None,
    ) -> ScheduledShutdownExecution:
        """Prepare RTC and cross the existing host-power boundary only on PASS.

        This method contains no shell/systemd power command. The only external
        power intent is the exact ``shutdown`` action passed to the narrow
        HostPowerRequester protocol after RTC verification succeeds.
        """

        prepared = self.prepare_scheduled_shutdown(now_utc)
        if not (
            prepared.shutdown_ready is True
            and prepared.rtc_alarm_armed is True
            and prepared.rtc_alarm_verified is True
            and prepared.rtc_alarm_value is not None
        ):
            return ScheduledShutdownExecution(
                state=prepared,
                host_power_requested=False,
                host_power_accepted=False,
                host_power_response=None,
                alert_code=prepared.alert_code,
                last_error=prepared.last_error,
            )

        try:
            response = host_power.request("shutdown")
        except Exception as exc:
            return self._host_power_failure(prepared, None, str(exc))

        if not isinstance(response, dict):
            return self._host_power_failure(
                prepared,
                None,
                "host-power returned a non-object response",
            )

        normalized = dict(response)
        accepted = (
            normalized.get("ok") is True
            and normalized.get("accepted") is True
            and normalized.get("action") == "shutdown"
        )
        if not accepted:
            return self._host_power_failure(
                prepared,
                normalized,
                f"host-power rejected scheduled shutdown: {normalized!r}",
            )

        return ScheduledShutdownExecution(
            state=prepared,
            host_power_requested=True,
            host_power_accepted=True,
            host_power_response=normalized,
            alert_code=None,
            last_error="",
        )

    def _host_power_failure(
        self,
        prepared: PowerSchedulerState,
        response: dict[str, object] | None,
        error: str,
    ) -> ScheduledShutdownExecution:
        clear_error = self._best_effort_clear_rtc()
        rtc_cleared = clear_error == ""
        full_error = error
        if clear_error:
            full_error = f"{error}; RTC cleanup failed: {clear_error}"

        failed_state = PowerSchedulerState(
            scheduled_shutdown_enabled=prepared.scheduled_shutdown_enabled,
            shutdown_ready=False,
            next_shutdown_at=prepared.next_shutdown_at,
            next_wake_at_local=prepared.next_wake_at_local,
            next_wake_at_utc=prepared.next_wake_at_utc,
            next_wake_reason=prepared.next_wake_reason,
            rtc_alarm_armed=False if rtc_cleared else prepared.rtc_alarm_armed,
            rtc_alarm_verified=False if rtc_cleared else prepared.rtc_alarm_verified,
            rtc_alarm_value=None if rtc_cleared else prepared.rtc_alarm_value,
            shutdown_inhibited_reason="host_power_request_failed",
            alert_code=HOST_POWER_REQUEST_FAILED,
            last_error=full_error,
        )
        return ScheduledShutdownExecution(
            state=failed_state,
            host_power_requested=True,
            host_power_accepted=False,
            host_power_response=response,
            alert_code=HOST_POWER_REQUEST_FAILED,
            last_error=full_error,
        )

    def _best_effort_clear_rtc(self) -> str:
        try:
            self._rtc.clear()
            if self._rtc.read_epoch() is not None:
                return "RTC wakealarm remained armed after clear"
        except Exception as exc:
            return str(exc)
        return ""

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
