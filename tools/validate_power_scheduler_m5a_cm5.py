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


class RecordingHostPower:
    """Non-actuating M5A boundary probe.

    It records the exact intent that would be sent to the existing privileged
    host-power client, but never opens its Unix socket and cannot power off CM5.
    """

    def __init__(self) -> None:
        self.actions: list[str] = []

    def request(self, action: str) -> dict[str, object]:
        self.actions.append(action)
        return {"ok": True, "accepted": True, "action": action, "m5a_probe": True}


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
        effective_profile="M5A_LAB_STANDBY",
        effective_mode=CalendarMode.STANDBY,
        rule_id="M5A_LAB_RULE",
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
    require(initial is None, f"existing RTC wakealarm must be empty before M5A, got {initial}")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    wake = now + timedelta(minutes=5)
    host_power = RecordingHostPower()
    scheduler = PowerScheduler(
        FixedCalendar(make_resolution(now, wake)),
        rtc,
        enabled=True,
        minimum_wake_lead_seconds=120,
    )

    result = scheduler.execute_scheduled_shutdown(host_power, now)
    expected_epoch = int(wake.timestamp())

    require(result.state.shutdown_ready is True, f"scheduler not ready: {result.to_dict()}")
    require(result.state.rtc_alarm_armed is True, "RTC was not reported armed")
    require(result.state.rtc_alarm_verified is True, "RTC was not reported verified")
    require(result.state.rtc_alarm_value == expected_epoch, "scheduler RTC epoch mismatch")
    require(rtc.read_epoch() == expected_epoch, "physical RTC read-back differs from scheduler")
    require(result.host_power_requested is True, "host-power boundary was not reached")
    require(result.host_power_accepted is True, "M5A host-power probe was not accepted")
    require(host_power.actions == ["shutdown"], f"unexpected host-power intents: {host_power.actions!r}")

    payload = {
        "ok": True,
        "validation": "power_scheduler_m5a_cm5",
        "scheduler_execution": result.to_dict(),
        "recorded_host_power_actions": host_power.actions,
        "physical_rtc_epoch": rtc.read_epoch(),
        "physical_power_action": False,
        "real_host_power_socket_used": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    rtc.clear()
    require(rtc.read_epoch() is None, "final RTC alarm did not clear")
    print("PASS: M5A verified RTC gate -> exact shutdown intent without host power action")
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
