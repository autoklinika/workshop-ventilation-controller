#!/usr/bin/env python3
"""Daily WVC CM5 power schedule: arm 08:00 RTC wake, then request safe host shutdown.

This program intentionally never controls fans/GPIO/HMI directly.
The existing wvc-host-power agent owns the safety sequence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Warsaw")
RTC_ALARM = Path("/sys/class/rtc/rtc0/wakealarm")
HOST_SOCKET = Path("/run/wvc-host-power/host-power.sock")
BOOTLOADER_CONFIG = ("/usr/bin/vcgencmd", "bootloader_config")


def next_wakeup(now: datetime) -> datetime:
    """Next 08:00 in Warsaw, allowing 15 minutes for an orderly shutdown."""
    local_now = now.astimezone(ZONE)
    wake = datetime.combine(local_now.date(), time(8, 0), tzinfo=ZONE)
    if (wake - local_now).total_seconds() < 900:
        wake = datetime.combine(local_now.date() + timedelta(days=1), time(8, 0), tzinfo=ZONE)
    return wake


def validate_hardware() -> None:
    if not RTC_ALARM.is_file():
        raise RuntimeError(f"RTC wakealarm missing: {RTC_ALARM}")
    config = subprocess.run(BOOTLOADER_CONFIG, check=True, capture_output=True, text=True, timeout=8).stdout
    for key, value in (("POWER_OFF_ON_HALT", "1"), ("WAKE_ON_GPIO", "0")):
        if re.search(rf"(?m)^{key}={value}\s*$", config) is None:
            raise RuntimeError(f"EEPROM bootloader configuration requires {key}={value}")
    if datetime.now(ZONE).year < 2025:
        raise RuntimeError("System clock is invalid; refusing scheduled shutdown")
    if not HOST_SOCKET.is_socket():
        raise RuntimeError(f"wvc-host-power socket unavailable: {HOST_SOCKET}")


def arm_wakeup(wake: datetime) -> int:
    epoch = int(wake.timestamp())
    RTC_ALARM.write_text("0\n", encoding="ascii")
    RTC_ALARM.write_text(f"{epoch}\n", encoding="ascii")
    observed = RTC_ALARM.read_text(encoding="ascii").strip()
    if not observed or abs(int(observed) - epoch) > 2:
        raise RuntimeError(f"RTC verification failed: expected {epoch}, observed {observed!r}")
    print(f"RTC_WAKE_ARMED local={wake.isoformat()} utc_epoch={epoch} readback={observed}", flush=True)
    return epoch


def request_safe_shutdown() -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(75)
        conn.connect(str(HOST_SOCKET))
        conn.sendall(b'{"action":"shutdown"}\n')
        buf = bytearray()
        while len(buf) < 8192 and b"\n" not in buf:
            piece = conn.recv(2048)
            if not piece:
                break
            buf.extend(piece)
    if not buf:
        raise RuntimeError("No response from wvc-host-power")
    response = json.loads(bytes(buf).split(b"\n", 1)[0])
    if response.get("ok") is not True or response.get("accepted") is not True:
        raise RuntimeError(f"Safe shutdown rejected by wvc-host-power: {response}")
    print("WVC_SAFE_SHUTDOWN_ACCEPTED_BY_HOST_POWER", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "arm-only", "shutdown"))
    args = parser.parse_args()
    try:
        validate_hardware()
        now = datetime.now(ZONE)
        wake = next_wakeup(now)
        print(f"WVC_SCHEDULE action={args.action} now={now.isoformat()} wake={wake.isoformat()}", flush=True)
        if args.action != "check":
            arm_wakeup(wake)
        if args.action == "shutdown":
            request_safe_shutdown()
        print("WVC_POWER_SCHEDULE_PASS", flush=True)
        return 0
    except Exception as exc:
        # Fail closed: a failed RTC preflight must never cause the CM5 to power off.
        print(f"WVC_POWER_SCHEDULE_FAIL: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
