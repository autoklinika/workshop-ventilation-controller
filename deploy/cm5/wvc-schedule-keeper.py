#!/usr/bin/env python3
"""WVC calendar keeper: preserve RTC wake and resume AUTO at a scheduled start.

Root-owned independent control-plane utility. 'plan' never actuates hardware.
'arm' reconciles RTC without touching fans; 'tick' additionally attempts AUTO
once per configured workday start, subject to hardware and operator interlocks.
"""
from __future__ import annotations

import argparse
from calendar import isleap
from datetime import date, datetime, time, timedelta, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import tempfile
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
POWER_SCRIPT = Path("/usr/local/libexec/wvc-power-schedule.py")
RTC_ALARM = Path("/sys/class/rtc/rtc0/wakealarm")
STATE_DIR = Path("/var/lib/wvc-scheduled-auto")
CLAIM_FILE = STATE_DIR / "scheduled-start-claim.json"
OLD_TICKET = STATE_DIR / "next-wake.json"
HOLD_FILE = Path("/var/lib/workshop-ventilation/active-auto-hold.json")
LOCK_FILE = Path("/run/wvc-schedule-keeper.lock")
MAX_LOOKAHEAD_DAYS = 370
WAKE_LEAD_SECONDS = 60
START_WINDOW_MINUTES = 20
ORDINARY_HOLDS = frozenset({
    "MANUAL_COMMAND_stop", "MANUAL_COMMAND_set", "MANUAL_COMMAND_aero-speed",
    "MANUAL_COMMAND_aero-airing", "OPERATOR_SELECTED_MANUAL",
    "BOOT_MANUAL_REQUIRES_EXPLICIT_AUTO_RESUME",
})


def core_request(command: Mapping[str, Any], path: Path = CORE_SOCKET) -> dict[str, Any]:
    if command.get("command") not in {"status", "autostart", "auto-resume"}:
        raise ValueError("unsupported core command")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(path))
        sock.sendall((json.dumps(dict(command), separators=(",", ":")) + "\n").encode())
        data = bytearray()
        while b"\n" not in data:
            part = sock.recv(4096)
            if not part:
                raise RuntimeError("core socket response incomplete")
            data.extend(part)
            if len(data) > 256 * 1024:
                raise RuntimeError("core socket response oversized")
    answer = json.loads(bytes(data).split(b"\n", 1)[0])
    if not isinstance(answer, dict) or answer.get("ok") is not True:
        raise RuntimeError("core rejected schedule request")
    return answer


def hhmm(value: Any) -> time:
    if not isinstance(value, str) or re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", value) is None:
        raise ValueError("invalid HH:MM")
    hour, minute = map(int, value.split(":"))
    if hour > 23:
        raise ValueError("invalid hour")
    return time(hour, minute)


def local_start(day: date, value: str) -> datetime:
    start = datetime.combine(day, hhmm(value), tzinfo=WARSAW)
    if start.astimezone(timezone.utc).astimezone(WARSAW).replace(fold=start.fold) != start:
        raise ValueError("nonexistent start time due to DST")
    return start


def validate_calendar(response: Mapping[str, Any], year: int) -> dict[str, Any]:
    entry = response.get("autostart")
    if not isinstance(entry, dict) or entry.get("available") is not True:
        raise ValueError("calendar unavailable")
    if entry.get("year") != year or type(entry.get("revision")) is not int:
        raise ValueError("calendar year/revision invalid")
    config = entry.get("config")
    if not isinstance(config, dict) or type(config.get("enabled")) is not bool or type(config.get("schedule_enabled")) is not bool:
        raise ValueError("calendar switches invalid")
    days = entry.get("days")
    if not isinstance(days, list) or len(days) != (366 if isleap(year) else 365):
        raise ValueError("calendar date count invalid")
    for offset, row in enumerate(days):
        day = date(year, 1, 1) + timedelta(days=offset)
        if not isinstance(row, dict) or row.get("date") != day.isoformat() or row.get("weekday") != day.isoweekday() or type(row.get("enabled")) is not bool:
            raise ValueError("calendar day integrity invalid")
        start, end = row.get("start_local"), row.get("end_local")
        if (start is None) != (end is None):
            raise ValueError("incomplete work hours")
        if start is not None and not hhmm(start) < hhmm(end):
            raise ValueError("invalid work window")
    return entry


def plan(now: datetime, loader: Callable[[int], dict[str, Any]]) -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone aware clock required")
    local = now.astimezone(WARSAW)
    cache: dict[int, dict[str, Any]] = {}

    def calendar(year: int) -> dict[str, Any]:
        if not 2025 <= year <= 2100:
            raise ValueError("unsupported calendar year")
        if year not in cache:
            cache[year] = validate_calendar(loader(year), year)
        return cache[year]

    current = calendar(local.year)
    cfg = current["config"]
    output: dict[str, Any] = {
        "now_local": local.isoformat(),
        "revision": current["revision"],
        "enabled": cfg["enabled"],
        "schedule_enabled": cfg["schedule_enabled"],
        "next_wake_local": None,
        "start_today_local": None,
        "end_today_local": None,
        "start_due": False,
        "reason": "disabled",
    }
    if not cfg["enabled"] or not cfg["schedule_enabled"]:
        return output

    today = current["days"][local.timetuple().tm_yday - 1]
    if today["enabled"] and today["start_local"] is not None:
        start = local_start(local.date(), today["start_local"])
        end = local_start(local.date(), today["end_local"])
        output["start_today_local"] = start.isoformat()
        output["end_today_local"] = end.isoformat()
        elapsed = (local.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
        output["start_due"] = 0 <= elapsed < min(START_WINDOW_MINUTES * 60, (end - start).total_seconds())
    for offset in range(MAX_LOOKAHEAD_DAYS + 1):
        day = local.date() + timedelta(days=offset)
        if day.year > 2100:
            break
        doc = calendar(day.year)
        if not doc["config"]["enabled"] or not doc["config"]["schedule_enabled"]:
            continue
        row = doc["days"][day.timetuple().tm_yday - 1]
        if row["enabled"] is not True or row["start_local"] is None:
            continue
        future = local_start(day, row["start_local"])
        if (future.astimezone(timezone.utc) - local.astimezone(timezone.utc)).total_seconds() < WAKE_LEAD_SECONDS:
            continue
        output["next_wake_local"] = future.isoformat()
        output["reason"] = "next_start_found"
        return output
    output["reason"] = "no_future_start"
    return output


def trusted_file(file: Path) -> None:
    details = file.stat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o022:
        raise RuntimeError(f"untrusted root helper: {file}")


def synced_clock() -> bool:
    import subprocess
    result = subprocess.run(["/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                            capture_output=True, text=True, check=True, timeout=5)
    return result.stdout.strip() == "yes"


def reconcile_rtc(next_wake: str | None, *, active_schedule: bool) -> str:
    if not synced_clock():
        raise RuntimeError("clock not synchronized; RTC untouched")
    raw = RTC_ALARM.read_text(encoding="ascii").strip()
    current = int(raw) if raw else None
    if next_wake is None:
        # Neither disabled nor empty schedules may retain an obsolete WVC alarm.
        if current is not None:
            RTC_ALARM.write_text("0\n", encoding="ascii")
            return "cleared_no_future" if active_schedule else "cleared_disabled"
        return "unchanged_no_future"
    wake = datetime.fromisoformat(next_wake)
    epoch = int(wake.timestamp())
    if current is not None and abs(current - epoch) <= 2:
        return "already_armed"
    trusted_file(POWER_SCRIPT)
    spec = importlib.util.spec_from_file_location("wvc_power_schedule_keeper", POWER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load trusted RTC helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_hardware()
    module.arm_wakeup(wake)
    observed = RTC_ALARM.read_text(encoding="ascii").strip()
    if not observed or abs(int(observed) - epoch) > 2:
        raise RuntimeError("RTC wakealarm readback invalid")
    return "armed"


def validate_state_directory(path: Path = STATE_DIR) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError("state directory must be root-owned 0700")


def claim_matches(claim: Mapping[str, Any], planned_start: str, revision: int) -> bool:
    return (claim.get("schema") == 1 and claim.get("start_local") == planned_start
            and claim.get("revision") == revision)


def load_claim() -> dict[str, Any] | None:
    validate_state_directory()
    try:
        details = CLAIM_FILE.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o077 or details.st_size > 512:
        raise RuntimeError("invalid scheduled-start claim")
    return json.loads(CLAIM_FILE.read_text(encoding="utf-8"))


def record_claim(planned_start: str, revision: int, result: str) -> None:
    validate_state_directory()
    data = json.dumps({"schema": 1, "start_local": planned_start,
                       "revision": revision, "result": result}, separators=(",", ":"))
    fd, temp = tempfile.mkstemp(prefix=".start-", dir=STATE_DIR)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, CLAIM_FILE)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def hold_before_start(hold: Mapping[str, Any], reason: str, start: datetime,
                      *, boot_start: datetime | None = None) -> bool:
    if reason not in ORDINARY_HOLDS or hold.get("reason") != reason or hold.get("fault_latched") is True:
        return False
    try:
        observed = datetime.fromisoformat(str(hold["at"]).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return False
        if observed < start.astimezone(timezone.utc):
            return True
    except (ValueError, KeyError, TypeError):
        return False
    # A scheduled RTC boot may create the initial BOOT_MANUAL HOLD after the start.
    return (reason == "BOOT_MANUAL_REQUIRES_EXPLICIT_AUTO_RESUME"
            and boot_start is not None and -timedelta(minutes=1) <=
            boot_start.astimezone(timezone.utc) - start.astimezone(timezone.utc) <= timedelta(minutes=7))


def safe_to_resume(state: Mapping[str, Any], hold: Mapping[str, Any], start: datetime) -> str:
    auto = state.get("active_auto")
    if not isinstance(auto, dict) or auto.get("enabled") is not True:
        return "rejected_auto_disabled"
    if auto.get("active") is True and auto.get("mode") == "AUTO":
        return "already_auto"
    if auto.get("fault_latched") is not False or auto.get("operator_action"):
        return "rejected_fault"
    if auto.get("hold") is not True or not hold_before_start(hold, str(auto.get("hold_reason")), start,
                                                           boot_start=kernel_boot_utc()):
        return "rejected_manual_or_unknown_hold"
    if any(str(a.get("severity", "")).lower() == "critical" for a in state.get("active_alarms") or []):
        return "rejected_alarm"
    if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
        return "waiting_dac"
    tacho = state.get("tacho") or {}
    if tacho.get("ready") is not True or tacho.get("worker_alive") is not True:
        return "waiting_tacho"
    aero = state.get("aero_bus") or {}
    if any(aero.get(k) is not True for k in ("ready", "online", "usable")):
        return "waiting_aero"
    nodes = {row.get("slave_address"): row for row in (state.get("sensor_bus") or {}).get("nodes") or []}
    for addr in (1, 2):
        node = nodes.get(addr) or {}
        if (node.get("online") is not True or node.get("usable") is not True
                or node.get("measurement_valid") is not True or node.get("measurement_stale") is not False):
            return f"waiting_sensor_{addr}"
    return "ready"


def kernel_boot_utc() -> datetime:
    for row in Path("/proc/stat").read_text(encoding="ascii").splitlines():
        if row.startswith("btime "):
            return datetime.fromtimestamp(int(row.split()[1]), tz=timezone.utc)
    raise RuntimeError("kernel boot time unavailable")


def maybe_start_auto(info: Mapping[str, Any]) -> str:
    if info.get("start_due") is not True:
        return "outside_start_window"
    start_iso = info.get("start_today_local")
    if not isinstance(start_iso, str):
        return "missing_start"
    revision = info["revision"]
    claim = load_claim()
    if claim is not None and claim_matches(claim, start_iso, revision):
        return "already_processed"
    # Avoid racing the older single-use RTC resume service at system startup.
    if OLD_TICKET.exists():
        return "waiting_legacy_resume"
    response = core_request({"command": "status"})
    state = response["state"]
    auto = state.get("active_auto") or {}
    if auto.get("active") is True and auto.get("mode") == "AUTO":
        record_claim(start_iso, revision, "already_auto")
        return "already_auto"
    try:
        hold = json.loads(HOLD_FILE.read_text(encoding="utf-8"))
        if not isinstance(hold, dict):
            raise ValueError("hold JSON not an object")
    except (OSError, ValueError) as exc:
        return f"rejected_hold_file_{type(exc).__name__}"
    status = safe_to_resume(state, hold, datetime.fromisoformat(start_iso))
    if status != "ready":
        return status
    # Claim BEFORE requesting actuation: a user STOP later in the same morning
    # must never be undone by another timer tick.
    record_claim(start_iso, revision, "attempted")
    output = core_request({"command": "auto-resume"})
    auto = output.get("active_auto") or {}
    if auto.get("active") is True and auto.get("hold") is False:
        return "resumed_auto"
    return "rejected_resume_not_confirmed"


def run(action: str) -> int:
    now = datetime.now(timezone.utc)
    info = plan(now, lambda year: core_request({"command": "autostart", "year": year}))
    print("WVC_KEEPER_PLAN " + json.dumps(info, separators=(",", ":")), flush=True)
    if action == "plan":
        return 0
    if os.geteuid() != 0:
        raise PermissionError("RTC keeper must run as root")
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = info["enabled"] and info["schedule_enabled"]
        result = reconcile_rtc(info["next_wake_local"], active_schedule=active)
        print("WVC_KEEPER_RTC " + result, flush=True)
        if action == "tick" and active:
            result = maybe_start_auto(info)
            print("WVC_KEEPER_AUTO " + result, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "arm", "tick"))
    args = parser.parse_args()
    try:
        return run(args.action)
    except Exception as exc:
        print(f"WVC_KEEPER_FAIL_CLOSED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
