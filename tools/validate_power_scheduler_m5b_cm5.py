#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

from ventilation_core.application.power_scheduler import PowerScheduler
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.infrastructure.rtc_wake import SysfsRtcWakeAlarm
from ventilation_core.web.host_power import HostPowerClient


WAKEALARM = Path("/sys/class/rtc/rtc0/wakealarm")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
UPTIME = Path("/proc/uptime")
STATE_PATH = Path(os.environ.get("M5B_STATE_PATH", "/var/tmp/wvc-power-scheduler-m5b-validation/state.json"))
TZ = ZoneInfo("Europe/Warsaw")
WAKE_DELAY = timedelta(minutes=5)
BOOT_TIME_TOLERANCE_SECONDS = 120


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


def read_boot_id() -> str:
    value = BOOT_ID.read_text(encoding="ascii").strip()
    require(bool(value), "kernel boot_id is empty")
    return value


def write_state(payload: dict[str, object]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, STATE_PATH)
    directory_fd = os.open(STATE_PATH.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def read_state() -> dict[str, object]:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"M5B state file is missing: {STATE_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"M5B state file is invalid JSON: {STATE_PATH}") from exc
    require(isinstance(payload, dict), "M5B state must be a JSON object")
    return payload


def make_resolution(now: datetime, next_wake: datetime) -> CalendarResolution:
    local_now = now.astimezone(TZ)
    local_wake = next_wake.astimezone(TZ)
    return CalendarResolution(
        available=True,
        timezone="Europe/Warsaw",
        evaluated_at_utc=now.astimezone(timezone.utc).isoformat(),
        local_time=local_now.isoformat(),
        phase=CalendarPhase.INACTIVE,
        effective_profile="M5B_LAB_STANDBY",
        effective_mode=CalendarMode.STANDBY,
        rule_id="M5B_LAB_RULE",
        current_period_start=None,
        current_period_end=None,
        next_transition=local_wake.isoformat(),
        next_transition_reason="START_PREVENTILATION",
        next_active_period=(local_wake + timedelta(minutes=30)).isoformat(),
        next_wake=local_wake.isoformat(),
    )


class PersistingRtc:
    def __init__(self, delegate: SysfsRtcWakeAlarm, state: dict[str, object]) -> None:
        self._delegate = delegate
        self._state = state

    def read_epoch(self):
        return self._delegate.read_epoch()

    def clear(self):
        self._delegate.clear()
        self._state["rtc_alarm_epoch"] = None
        self._state["rtc_alarm_verified"] = False
        self._state["stage"] = "rtc_cleared"
        write_state(self._state)

    def arm(self, wake_at: datetime, *, minimum_lead_seconds: int = 60):
        result = self._delegate.arm(wake_at, minimum_lead_seconds=minimum_lead_seconds)
        self._state["rtc_alarm_epoch"] = result.verified_epoch
        self._state["rtc_alarm_verified"] = result.verified is True
        self._state["stage"] = "rtc_verified"
        write_state(self._state)
        return result


class PersistingHostPower:
    def __init__(self, delegate: HostPowerClient, state: dict[str, object]) -> None:
        self._delegate = delegate
        self._state = state

    def request(self, action: str) -> dict[str, object]:
        require(action == "shutdown", f"M5B permits only shutdown intent, got {action!r}")
        self._state["host_power_action"] = action
        self._state["host_power_request_started_at"] = datetime.now(timezone.utc).isoformat()
        self._state["stage"] = "host_power_request_started"
        write_state(self._state)

        response = self._delegate.request(action)
        self._state["host_power_response"] = response
        if (
            isinstance(response, dict)
            and response.get("ok") is True
            and response.get("accepted") is True
            and response.get("action") == "shutdown"
        ):
            self._state["stage"] = "host_power_accepted"
            self._state["host_power_accepted_at"] = datetime.now(timezone.utc).isoformat()
        else:
            self._state["stage"] = "host_power_rejected"
        write_state(self._state)
        return response


def prepare() -> int:
    rtc_raw = SysfsRtcWakeAlarm(WAKEALARM)
    require(rtc_raw.read_epoch() is None, "existing RTC wakealarm must be empty before M5B")
    require(not STATE_PATH.exists(), f"stale M5B state already exists: {STATE_PATH}")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    wake = now + WAKE_DELAY
    expected_epoch = int(wake.timestamp())
    branch_sha = os.environ.get("M5B_EXPECTED_BRANCH_SHA", "")
    main_sha = os.environ.get("M5B_EXPECTED_MAIN_SHA", "")
    require(bool(branch_sha), "M5B_EXPECTED_BRANCH_SHA is required")
    require(bool(main_sha), "M5B_EXPECTED_MAIN_SHA is required")

    state: dict[str, object] = {
        "validation": "power_scheduler_m5b_cm5",
        "stage": "prepare_started",
        "created_at_utc": now.isoformat(),
        "before_boot_id": read_boot_id(),
        "expected_wake_at_utc": wake.isoformat(),
        "expected_wake_epoch": expected_epoch,
        "branch_sha": branch_sha,
        "main_sha": main_sha,
        "rtc_alarm_epoch": None,
        "rtc_alarm_verified": False,
        "host_power_action": None,
        "host_power_response": None,
    }
    write_state(state)

    rtc = PersistingRtc(rtc_raw, state)
    host_power = PersistingHostPower(HostPowerClient(), state)
    scheduler = PowerScheduler(
        FixedCalendar(make_resolution(now, wake)),
        rtc,
        enabled=True,
        minimum_wake_lead_seconds=120,
    )

    result = scheduler.execute_scheduled_shutdown(host_power, now)
    require(result.state.shutdown_ready is True, f"scheduler not ready: {result.to_dict()}")
    require(result.state.rtc_alarm_verified is True, "RTC was not verified")
    require(result.state.rtc_alarm_value == expected_epoch, "RTC epoch mismatch")
    require(result.host_power_requested is True, "real host-power boundary was not reached")
    require(result.host_power_accepted is True, f"host-power did not accept shutdown: {result.to_dict()}")
    require(rtc_raw.read_epoch() == expected_epoch, "RTC wakealarm changed after host-power acceptance")

    state["scheduler_execution"] = result.to_dict()
    state["stage"] = "host_power_accepted"
    write_state(state)
    os.sync()

    print(json.dumps({
        "ok": True,
        "validation": "power_scheduler_m5b_cm5",
        "phase": "prepare",
        "expected_wake_at_utc": wake.isoformat(),
        "expected_wake_epoch": expected_epoch,
        "real_host_power_socket_used": True,
        "host_power_accepted": True,
        "message": "CM5 poweroff accepted; process should be terminated by real host shutdown before returning",
    }, indent=2, sort_keys=True), flush=True)
    print("PASS: M5B RTC verified and real wvc-host-power accepted shutdown; waiting for host poweroff", flush=True)

    # A successful M5B PREPARE never returns normally: the real host-power agent
    # powers the CM5 off.  If the process survives for 60 s, treat that as a
    # failed power action, clear RTC, and let the harness restore host-power.
    time.sleep(60)
    try:
        rtc_raw.clear()
    finally:
        state["stage"] = "poweroff_timeout"
        write_state(state)
    raise RuntimeError("CM5 remained running 60 s after accepted host-power shutdown")


def verify() -> int:
    state = read_state()
    require(state.get("validation") == "power_scheduler_m5b_cm5", "unexpected M5B state identity")
    require(state.get("stage") == "host_power_accepted", f"M5B did not persist host-power acceptance: {state.get('stage')!r}")
    require(state.get("host_power_action") == "shutdown", "M5B state does not contain exact shutdown action")

    response = state.get("host_power_response")
    require(isinstance(response, dict), "M5B state has no host-power response")
    require(response.get("ok") is True, f"host-power response not OK: {response!r}")
    require(response.get("accepted") is True, f"host-power response not accepted: {response!r}")
    require(response.get("action") == "shutdown", f"host-power response action mismatch: {response!r}")
    require(state.get("rtc_alarm_verified") is True, "M5B state does not prove RTC verification")

    before_boot_id = state.get("before_boot_id")
    require(isinstance(before_boot_id, str) and before_boot_id, "before_boot_id missing")
    current_boot_id = read_boot_id()
    require(current_boot_id != before_boot_id, "boot_id did not change; full power cycle not proven")

    expected_epoch = state.get("expected_wake_epoch")
    require(isinstance(expected_epoch, int), "expected_wake_epoch missing")
    uptime_seconds = float(UPTIME.read_text(encoding="ascii").split()[0])
    estimated_boot_epoch = time.time() - uptime_seconds
    delta = abs(estimated_boot_epoch - expected_epoch)
    require(
        delta <= BOOT_TIME_TOLERANCE_SECONDS,
        "CM5 boot time is not close enough to programmed RTC wake: "
        f"estimated_boot_epoch={estimated_boot_epoch:.0f}, expected={expected_epoch}, delta={delta:.1f}s",
    )

    rtc = SysfsRtcWakeAlarm(WAKEALARM)
    require(rtc.read_epoch() is None, f"RTC wakealarm should be consumed/empty after wake, got {rtc.read_epoch()}")

    state["after_boot_id"] = current_boot_id
    state["estimated_boot_epoch"] = int(estimated_boot_epoch)
    state["rtc_boot_delta_seconds"] = round(delta, 1)
    state["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["stage"] = "verified"
    write_state(state)

    print(json.dumps({
        "ok": True,
        "validation": "power_scheduler_m5b_cm5",
        "phase": "verify",
        "before_boot_id": before_boot_id,
        "after_boot_id": current_boot_id,
        "expected_wake_epoch": expected_epoch,
        "estimated_boot_epoch": int(estimated_boot_epoch),
        "rtc_boot_delta_seconds": round(delta, 1),
        "wakealarm_empty": True,
        "host_power_response": response,
    }, indent=2, sort_keys=True))
    print("PASS: M5B full poweroff -> RTC wake cycle verified")
    return 0


def main() -> int:
    require(len(sys.argv) == 2 and sys.argv[1] in {"prepare", "verify"}, "usage: validate_power_scheduler_m5b_cm5.py prepare|verify")
    if sys.argv[1] == "prepare":
        return prepare()
    return verify()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
