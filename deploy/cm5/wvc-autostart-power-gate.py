#!/usr/bin/env python3
"""WVC scheduled host-power gate.

This trusted root-owned script is called by the existing wvc-auto-poweroff
systemd service. It reads the *authoritative* Autostart calendar through the
localhost WVC API and never writes GPIO, fan setpoints or RTC itself.

Only at the exact scheduled daily close does it call the existing root-owned
wvc-power-schedule.py functions: hardware preflight, RTC alarm/readback, and
wvc-host-power safe shutdown.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Warsaw")
BASE_URL = "http://127.0.0.1:18091/api/v1/autostart/"
TRUSTED_POWER_SCRIPT = Path("/usr/local/libexec/wvc-power-schedule.py")
TRUSTED_AUTO_RESUME_SCRIPT = Path("/usr/local/libexec/wvc-rtc-auto-resume.py")
MIN_LEAD_SECONDS = 900
MAX_FUTURE_DAYS = 370


@dataclass(frozen=True)
class Plan:
    now_local: str
    configuration_revision: int | None
    autostart_enabled: bool
    schedule_enabled: bool
    due_now: bool
    next_wake_local: str | None
    reason: str
    start_local: str | None = None
    end_local: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


# No environment proxy and no HTTP redirect from the loopback-only API.
API_OPENER = build_opener(ProxyHandler({}), _NoRedirect())


def fetch_calendar(year: int) -> dict[str, Any]:
    if type(year) is not int or not 2025 <= year <= 2100:
        raise ValueError("unsupported autostart year")
    # Loopback only, bounded HTTP response, timeout. Never use remote URLs.
    with API_OPENER.open(BASE_URL + str(year), timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("Autostart API did not return HTTP 200")
        raw = response.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError("Autostart API response exceeds maximum length")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError("Autostart API returned a failure")
    entry = payload.get("autostart")
    if not isinstance(entry, dict) or entry.get("available") is not True:
        raise RuntimeError("Autostart is unavailable")
    if entry.get("year") != year or type(entry.get("revision")) is not int:
        raise ValueError("Autostart API year or revision mismatch")
    config = entry.get("config")
    if not isinstance(config, dict) or type(config.get("enabled")) is not bool or type(config.get("schedule_enabled")) is not bool:
        raise ValueError("Autostart API has invalid main switches")
    days = entry.get("days")
    from calendar import isleap
    expected = 366 if isleap(year) else 365
    if not isinstance(days, list) or len(days) != expected:
        raise ValueError("Autostart API has missing calendar dates")
    first = date(year, 1, 1)
    for offset, row in enumerate(days):
        current = first + timedelta(days=offset)
        if not isinstance(row, dict) or row.get("date") != current.isoformat() or row.get("weekday") != current.isoweekday() or type(row.get("enabled")) is not bool:
            raise ValueError("Autostart API day integrity check failed")
        start, end = row.get("start_local"), row.get("end_local")
        if (start is None) != (end is None):
            raise ValueError("Autostart API has incomplete time")
        if start is not None and (not valid_hhmm(start) or not valid_hhmm(end) or start >= end):
            raise ValueError("Autostart API has invalid work hours")
    return entry


def valid_hhmm(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    h, m = value[:2], value[3:]
    return h.isascii() and m.isascii() and h.isdecimal() and m.isdecimal() and 0 <= int(h) <= 23 and 0 <= int(m) < 60


def local_wall_time(day: date, hhmm: str) -> datetime:
    if not valid_hhmm(hhmm):
        raise ValueError("invalid HH:MM")
    hour, minute = map(int, hhmm.split(":"))
    local = datetime.combine(day, time(hour, minute), tzinfo=ZONE)
    # Spring DST gaps cannot be used as RTC alarms. Fall folds use first occurrence.
    if local.astimezone(timezone.utc).astimezone(ZONE).replace(fold=local.fold) != local:
        raise ValueError("nonexistent local time during DST transition")
    return local


def build_plan(now: datetime, loader: Callable[[int], dict[str, Any]] = fetch_calendar) -> Plan:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(ZONE)
    today = local.date()
    if not 2025 <= today.year <= 2099:
        raise ValueError("current year unsupported for calculating next wake")
    calendar = loader(today.year)
    config = calendar["config"]
    enabled = config["enabled"]
    schedule_enabled = config["schedule_enabled"]
    revision = calendar["revision"]
    def outcome(reason: str, *, due: bool = False, wake: datetime | None = None, row: dict[str, Any] | None = None) -> Plan:
        return Plan(
            now_local=local.isoformat(),
            configuration_revision=revision,
            autostart_enabled=enabled,
            schedule_enabled=schedule_enabled,
            due_now=due,
            next_wake_local=None if wake is None else wake.isoformat(),
            reason=reason,
            start_local=None if row is None else row.get("start_local"),
            end_local=None if row is None else row.get("end_local"),
        )
    if not enabled:
        return outcome("autostart_disabled")
    if not schedule_enabled:
        return outcome("schedule_disabled")

    rows = {item["date"]: item for item in calendar["days"]}
    row = rows[today.isoformat()]
    if not row["enabled"]:
        return outcome("non_working_day", row=row)
    if row["start_local"] is None or row["end_local"] is None:
        return outcome("working_day_without_hours", row=row)

    end = local_wall_time(today, row["end_local"])
    delta = (local.astimezone(timezone.utc) - end.astimezone(timezone.utc)).total_seconds()
    if not 0 <= delta < 60:
        return outcome("outside_close_minute", row=row)

    next_year_calendar = None
    for offset in range(1, MAX_FUTURE_DAYS + 1):
        day = today + timedelta(days=offset)
        # The calendar API covers the current year and the next year only.
        # Never misindex a third year through the second-year snapshot.
        if day.year > today.year + 1:
            break
        if day.year != today.year and next_year_calendar is None:
            next_year_calendar = loader(day.year)
            if next_year_calendar["config"] != config or next_year_calendar["revision"] != revision:
                raise ValueError("Autostart calendar configuration changed during lookup")
        source = calendar if day.year == today.year else next_year_calendar
        assert source is not None
        future = source["days"][day.timetuple().tm_yday - 1]
        if not future["enabled"] or future["start_local"] is None or future["end_local"] is None:
            continue
        wake = local_wall_time(day, future["start_local"])
        if (wake.astimezone(timezone.utc) - local.astimezone(timezone.utc)).total_seconds() < MIN_LEAD_SECONDS:
            continue
        return outcome("due", due=True, wake=wake, row=row)
    return outcome("next_wake_missing", row=row)


def trusted_existing_shutdown(wake: datetime) -> None:
    """Invoke unchanged existing RTC and host-power functions at the approved close."""
    if not TRUSTED_POWER_SCRIPT.is_file():
        raise RuntimeError("Existing root-owned host power script is missing")
    file_stat = TRUSTED_POWER_SCRIPT.stat()
    if file_stat.st_uid != 0 or bool(file_stat.st_mode & 0o022):
        raise RuntimeError("Existing host power script has insecure ownership or mode")
    spec = importlib.util.spec_from_file_location("wvc_trusted_power_schedule", TRUSTED_POWER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Existing host power script cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_hardware()
    module.arm_wakeup(wake)
    module.request_safe_shutdown()


def prepare_next_boot_auto_resume(wake: datetime, revision: int) -> bool:
    """One-time authorization only if AUTO was running before planned poweroff.

    The existing safe host-power STOP produces a persistent MANUAL_COMMAND
    HOLD. A separately installed, boot-only service may restore AUTO after
    the *next* expected wake, subject to the original AUTO resume interlocks.
    """
    if not TRUSTED_AUTO_RESUME_SCRIPT.is_file():
        raise RuntimeError("Scheduled AUTO resume service is not installed")
    info = TRUSTED_AUTO_RESUME_SCRIPT.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError("Scheduled AUTO resume helper has insecure ownership")
    spec = importlib.util.spec_from_file_location(
        "wvc_scheduled_auto_resume", TRUSTED_AUTO_RESUME_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load installed scheduled AUTO helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # Discard any previous one-shot ticket before the shutdown decision.
    module.clear_ticket()
    response = module.core_request({"command": "status"})
    state = response.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Core state unavailable before scheduled shutdown")
    if not module.auto_pre_shutdown_active(state):
        print("WVC_RTC_AUTO_RESUME_SKIP_NOT_ACTIVE_BEFORE_SHUTDOWN", flush=True)
        return False
    ticket = module.make_ticket(
        wake, revision, now=datetime.now(timezone.utc),
        source_boot_id=module.boot_id(),
    )
    module.write_ticket(ticket)
    print("WVC_RTC_AUTO_RESUME_TICKET_ARMED_NEXT_BOOT", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "tick"))
    args = parser.parse_args()
    try:
        plan = build_plan(datetime.now(timezone.utc))
        print("WVC_AUTOSTART_PLAN " + json.dumps(plan.to_dict(), separators=(",", ":"), ensure_ascii=False), flush=True)
        if args.action == "plan" or not plan.due_now:
            return 0
        if plan.next_wake_local is None:
            raise RuntimeError("Due shutdown with no verified next wake: fail closed")
        # Explicit timer service dispatch only; this check does not change RTC.
        wake = datetime.fromisoformat(plan.next_wake_local)
        if plan.configuration_revision is None:
            raise RuntimeError("Autostart revision is required for scheduled AUTO ticket")
        marked = prepare_next_boot_auto_resume(wake, plan.configuration_revision)
        try:
            trusted_existing_shutdown(wake)
        except BaseException:
            # If safe shutdown fails, never leave a future AUTO grant behind.
            if marked:
                try:
                    # The helper is already installed if a ticket was marked.
                    from pathlib import Path as _Path
                    _Path("/var/lib/wvc-scheduled-auto/next-wake.json").unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        print("WVC_AUTOSTART_SHUTDOWN_ACCEPTED_BY_EXISTING_HOST_POWER", flush=True)
        return 0
    except Exception as exc:
        print(f"WVC_AUTOSTART_FAIL_CLOSED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
