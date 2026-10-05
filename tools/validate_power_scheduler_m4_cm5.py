#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from ventilation_core.application.power_scheduler import PowerScheduler
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.infrastructure.rtc_wake import SysfsRtcWakeAlarm


WAKEALARM = Path("/sys/class/rtc/rtc0/wakealarm")
TZ = ZoneInfo("Europe/Warsaw")


class FixedCalendar:
    def __init__(self, resolution: CalendarResolution) -> None:
        self._resolution = resolution

    def resolve(self, now_utc=None):
        return self._resolution

    def configuration(self, now_utc=None):
        raise NotImplementedError

    def replace_configuration(self, payload):
        raise NotImplementedError

    def close(self):
        return None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def make_resolution(now: datetime, next_wake: datetime) -> CalendarResolution:
    local_now = now.astimezone(TZ)
    local_wake = next_wake.astimezone(TZ)
    return CalendarResolution(
        available=True,
        timezone="Europe/Warsaw",
        evaluated_at_utc=now.astimezone(timezone.utc).isoformat(),
        local_time=local_now.isoformat(),
        phase=CalendarPhase.INACTIVE,
        effective_profile="M4_LAB_STANDBY",
        effective_mode=CalendarMode.STANDBY,
        rule_id="M4_LAB_RULE",
        current_period_start=None,
        current_period_end=None,
        next_transition=local_wake.isoformat(),
        next_transition_reason="START_PREVENTILATION",
        next_active_period=(local_wake + timedelta(minutes=30)).isoformat(),
        next_wake=local_wake.isoformat(),
    )


def main() -> int:
    rtc = SysfsRtcWakeAlarm(WAKEALARM)
    initial = rtc.read_epoch()
    require(initial is None, f"existing RTC wakealarm must be empty before M4 validation, got {initial}")

    direct_target = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=3)
    direct = rtc.arm(direct_target, minimum_lead_seconds=60)
    require(direct.verified, "direct RTC adapter verification is false")
    require(rtc.read_epoch() == int(direct_target.timestamp()), "direct RTC read-back differs")
    rtc.clear()
    require(rtc.read_epoch() is None, "direct RTC alarm did not clear")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    scheduler_target = now + timedelta(minutes=5)
    scheduler = PowerScheduler(
        FixedCalendar(make_resolution(now, scheduler_target)),
        rtc,
        enabled=True,
        minimum_wake_lead_seconds=120,
    )
    state = scheduler.prepare_scheduled_shutdown(now)
    require(state.shutdown_ready is True, f"Power Scheduler is not ready: {state.to_dict()}")
    require(state.rtc_alarm_armed is True, "Power Scheduler did not report RTC armed")
    require(state.rtc_alarm_verified is True, "Power Scheduler did not report RTC verified")
    require(state.rtc_alarm_value == int(scheduler_target.timestamp()), "Power Scheduler RTC epoch mismatch")
    require(rtc.read_epoch() == int(scheduler_target.timestamp()), "physical RTC differs from scheduler result")

    result = {
        "ok": True,
        "validation": "power_scheduler_m4_cm5",
        "direct_rtc": direct.to_dict(),
        "scheduler": state.to_dict(),
        "physical_power_action": False,
        "host_power_requested": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    rtc.clear()
    require(rtc.read_epoch() is None, "final RTC alarm did not clear")
    print("PASS: Power Scheduler M4 CM5 RTC arm/read-back/clear validated without host shutdown")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            SysfsRtcWakeAlarm(WAKEALARM).clear()
        except Exception:
            pass
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
