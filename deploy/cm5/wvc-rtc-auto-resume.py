#!/usr/bin/env python3
"""Single-use AUTO restoration after a scheduled WVC RTC wake.

Privileged boot-only supervisor. Never directly writes EC/AERO/RTC/GPIO.
It uses the existing ventilation-core 'auto-resume' command only after a
verified planned shutdown ticket, next-boot ID, a narrow wake window,
matching Autostart revision, persistent STOP-related HOLD and full health.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
TICKET_DIR = Path("/var/lib/wvc-scheduled-auto")
TICKET_PATH = TICKET_DIR / "next-wake.json"
CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
ALLOWED_SHUTDOWN_HOLDS = frozenset({
    "MANUAL_COMMAND_stop", "MANUAL_COMMAND_aero-airing", "MANUAL_COMMAND_aero-speed"
})
ALLOWED_FIELDS = frozenset({
    "schema_version", "created_utc", "wake_utc", "source_boot_id", "calendar_revision"
})
MAX_BOOT_DELAY = timedelta(minutes=20)
MAX_SCHEDULE_SPAN = timedelta(days=14)
RETRY_SECONDS = 4
READY_DEADLINE_SECONDS = 150


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def boot_id() -> str:
    value = BOOT_ID_PATH.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise RuntimeError("invalid kernel boot ID")
    return value


def core_request(command: Mapping[str, Any], socket_path: Path = CORE_SOCKET) -> dict[str, Any]:
    if command.get("command") not in {"status", "autostart", "auto-resume"}:
        raise ValueError("unsupported scheduled-resume command")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(str(socket_path))
        conn.sendall((json.dumps(dict(command), separators=(",", ":")) + "\n").encode())
        data = bytearray()
        while b"\n" not in data:
            fragment = conn.recv(4096)
            if not fragment:
                raise RuntimeError("core response was truncated")
            data.extend(fragment)
            if len(data) > 2 * 1024 * 1024:
                raise RuntimeError("oversized core response")
    result = json.loads(data.split(b"\n", 1)[0])
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("core rejected scheduled resume request")
    return result


def auto_pre_shutdown_active(state: Mapping[str, Any]) -> bool:
    auto = state.get("active_auto")
    if not isinstance(auto, dict):
        raise ValueError("active_auto snapshot not available")
    if auto.get("enabled") is not True:
        return False
    if auto.get("active") is not True or auto.get("mode") != "AUTO":
        return False
    if auto.get("hold") is not False or auto.get("fault_latched") is not False:
        return False
    if any(str(a.get("severity", "")).lower() == "critical"
           for a in state.get("active_alarms") or []):
        return False
    return True


def make_ticket(wake: datetime, revision: int, *, now: datetime, source_boot_id: str) -> dict[str, Any]:
    wake_utc = _utc(wake)
    created_utc = _utc(now)
    span = wake_utc - created_utc
    if not timedelta(minutes=15) <= span <= MAX_SCHEDULE_SPAN:
        raise ValueError("wake time outside permitted planned interval")
    if type(revision) is not int or revision < 1:
        raise ValueError("calendar revision must be positive")
    if not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", source_boot_id):
        raise ValueError("invalid origin boot ID")
    return {
        "schema_version": 1,
        "created_utc": created_utc.isoformat(),
        "wake_utc": wake_utc.isoformat(),
        "source_boot_id": source_boot_id,
        "calendar_revision": revision,
    }


def validate_ticket(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ALLOWED_FIELDS or value.get("schema_version") != 1:
        raise ValueError("invalid ticket shape/version")
    if type(value.get("calendar_revision")) is not int:
        raise ValueError("invalid ticket revision")
    created = _utc(datetime.fromisoformat(value["created_utc"]))
    wake = _utc(datetime.fromisoformat(value["wake_utc"]))
    return make_ticket(wake, value["calendar_revision"], now=created,
                       source_boot_id=value["source_boot_id"])


def trusted_directory(path: Path) -> None:
    root = path.parent
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError("scheduled-resume directory must be root-owned 0700")


def write_ticket(ticket: Mapping[str, Any], path: Path = TICKET_PATH) -> None:
    trusted_directory(path)
    data = json.dumps(validate_ticket(dict(ticket)), separators=(",", ":"))
    fd, temp = tempfile.mkstemp(prefix=".ticket-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def clear_ticket(path: Path = TICKET_PATH) -> None:
    trusted_directory(path)
    path.unlink(missing_ok=True)


def read_ticket(path: Path = TICKET_PATH) -> dict[str, Any] | None:
    trusted_directory(path)
    try:
        details = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o077:
        raise ValueError("ticket must be root-owned regular 0600 file")
    if details.st_size > 2048:
        raise ValueError("oversized ticket")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        value = json.load(stream)
    return validate_ticket(value)


def ticket_wake_allowed(ticket: Mapping[str, Any], *, now: datetime,
                        current_boot_id: str, boot_start: datetime | None = None) -> str:
    value = validate_ticket(dict(ticket))
    if current_boot_id == value["source_boot_id"]:
        return "same_boot"
    expected = datetime.fromisoformat(value["wake_utc"])
    started = _utc(boot_start if boot_start is not None else boot_start_utc())
    # Boot must itself occur near the programmed RTC alarm, not hours before.
    startup_delta = started - expected
    if not -timedelta(minutes=1) <= startup_delta <= timedelta(minutes=7):
        return "outside_boot_window"
    elapsed = _utc(now) - expected
    if timedelta(0) <= elapsed <= MAX_BOOT_DELAY:
        return "expected_window"
    return "outside_expected_window"


def boot_start_utc() -> datetime:
    """Kernel boot epoch; prevents a manually early-started CM5 from later
    satisfying the 08:00 clock window just by remaining on until 08:00.
    """
    for line in Path("/proc/stat").read_text(encoding="ascii").splitlines():
        if line.startswith("btime "):
            epoch = int(line.split()[1])
            return datetime.fromtimestamp(epoch, tz=timezone.utc)
    raise RuntimeError("kernel boot timestamp unavailable")


def synced_clock() -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            check=True, capture_output=True, text=True, timeout=4,
        )
        return result.stdout.strip() == "yes"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def autostart_matches(ticket: Mapping[str, Any], response: Mapping[str, Any]) -> bool:
    doc = response.get("autostart")
    if not isinstance(doc, dict) or doc.get("available") is not True:
        return False
    cfg = doc.get("config") or {}
    if (doc.get("revision") != ticket["calendar_revision"] or
        cfg.get("enabled") is not True or cfg.get("schedule_enabled") is not True):
        return False
    expected = datetime.fromisoformat(ticket["wake_utc"]).astimezone(WARSAW)
    if doc.get("year") != expected.year:
        return False
    for day in doc.get("days") or []:
        if day.get("date") == expected.date().isoformat():
            return (day.get("enabled") is True and
                    day.get("start_local") == expected.strftime("%H:%M"))
    return False


def resume_preflight(state: Mapping[str, Any]) -> str:
    auto = state.get("active_auto")
    if not isinstance(auto, dict) or auto.get("enabled") is not True:
        return "rejected_auto_disabled"
    if auto.get("fault_latched") is True or auto.get("operator_action"):
        return "rejected_fault"
    if auto.get("hold") is not True or auto.get("hold_reason") not in ALLOWED_SHUTDOWN_HOLDS:
        return "rejected_operator_or_unknown_hold"
    if any(str(a.get("severity", "")).lower() == "critical"
           for a in state.get("active_alarms") or []):
        return "rejected_critical_alarm"
    if not state.get("hardware_ready") or not state.get("output_state_known"):
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
        if any(node.get(key) is not expected for key, expected in (
            ("online", True), ("usable", True),
            ("measurement_valid", True), ("measurement_stale", False),
        )):
            return f"waiting_sensor_{addr}"
    return "ready"


def scheduled_resume(path: Path = TICKET_PATH) -> str:
    if os.geteuid() != 0:
        raise PermissionError("scheduled AUTO boot service must run as root")
    ticket = read_ticket(path)
    if ticket is None:
        return "no_ticket"
    if ticket["source_boot_id"] == boot_id():
        return "same_boot"

    deadline = time.monotonic() + READY_DEADLINE_SECONDS
    last_reason = "not_started"
    while time.monotonic() < deadline:
        if not synced_clock():
            last_reason = "waiting_clock_sync"
            time.sleep(RETRY_SECONDS)
            continue
        if ticket_wake_allowed(ticket, now=datetime.now(timezone.utc),
                               current_boot_id=boot_id()) != "expected_window":
            clear_ticket(path)
            return "rejected_boot_window"
        try:
            start_local = datetime.fromisoformat(ticket["wake_utc"]).astimezone(WARSAW)
            calendar = core_request({"command": "autostart", "year": start_local.year})
            if not autostart_matches(ticket, calendar):
                clear_ticket(path)
                return "rejected_calendar_or_revision"
            status = core_request({"command": "status"})["state"]
            reason = resume_preflight(status)
            if reason.startswith("rejected_"):
                clear_ticket(path)
                return reason
            if reason != "ready":
                last_reason = reason
                time.sleep(RETRY_SECONDS)
                continue
            # Consume once *before* issuing the existing AUTO command.
            clear_ticket(path)
            result = core_request({"command": "auto-resume"})
            auto = result.get("active_auto") or {}
            if auto.get("active") is not True or auto.get("hold") is not False:
                return "rejected_resume_not_confirmed"
            return "resumed_auto"
        except (RuntimeError, OSError, KeyError, ValueError, TypeError) as exc:
            last_reason = f"waiting_core_{type(exc).__name__}"
            time.sleep(RETRY_SECONDS)
    clear_ticket(path)
    return f"timeout_{last_reason}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "run"))
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            print(f"WVC_RTC_AUTO_RESUME_INSPECT boot_id={boot_id()} ticket_exists={TICKET_PATH.exists()}")
            return 0
        result = scheduled_resume()
        print(f"WVC_RTC_AUTO_RESUME_RESULT {result}", flush=True)
        # Valid reasons for no auto; service should not endlessly retry.
        return 0 if result in {"resumed_auto", "no_ticket", "same_boot"} else 1
    except Exception as exc:
        print(f"WVC_RTC_AUTO_RESUME_FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
