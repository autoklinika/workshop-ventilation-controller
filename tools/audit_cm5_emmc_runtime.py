#!/usr/bin/env python3
"""Read-only runtime audit of writes to the CM5 eMMC root filesystem."""

from __future__ import annotations

import argparse
import os
import stat
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--top-processes", type=int, default=30)
    return parser.parse_args()


def mmc_written_sectors(block: str = "mmcblk0") -> int | None:
    with open("/proc/diskstats", encoding="utf-8") as handle:
        for line in handle:
            fields = line.split()
            if len(fields) >= 10 and fields[2] == block:
                return int(fields[9])
    return None


def uptime_seconds() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, IndexError, ValueError):
        return None


def filesystem_snapshot() -> dict[str, tuple[int, int, int]]:
    result: dict[str, tuple[int, int, int]] = {}
    root_dev = os.stat("/").st_dev
    skip = {"/proc", "/sys", "/dev", "/run"}

    for dirpath, dirnames, filenames in os.walk("/", topdown=True, followlinks=False):
        if dirpath in skip:
            dirnames[:] = []
            continue

        kept: list[str] = []
        for name in dirnames:
            path = os.path.join(dirpath, name)
            try:
                item = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISLNK(item.st_mode):
                continue
            if item.st_dev == root_dev:
                kept.append(name)
        dirnames[:] = kept

        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                item = os.lstat(path)
            except OSError:
                continue
            if item.st_dev != root_dev or not stat.S_ISREG(item.st_mode):
                continue
            result[path] = (item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    return result


def process_writes() -> dict[tuple[str, str], tuple[int, str]]:
    result: dict[tuple[str, str], tuple[int, str]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat_fields = (entry / "stat").read_text(encoding="utf-8").split()
            starttime = stat_fields[21]
            io_values: dict[str, int] = {}
            for line in (entry / "io").read_text(encoding="utf-8").splitlines():
                key, value = line.split(":", 1)
                io_values[key.strip()] = int(value.strip())
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
            cmd = command.decode(errors="replace").strip()
            if not cmd:
                cmd = (entry / "comm").read_text(encoding="utf-8").strip()
            result[(entry.name, starttime)] = (io_values.get("write_bytes", 0), cmd)
        except (OSError, IndexError, ValueError):
            continue
    return result


def main() -> int:
    args = parse_args()
    if args.duration < 1:
        raise SystemExit("--duration must be >= 1")
    if os.geteuid() != 0:
        raise SystemExit("run as root: sudo ./tools/audit_cm5_emmc_runtime.py")

    start_uptime = uptime_seconds()

    print("===== EMMC RUNTIME WRITE AUDIT =====")
    print("Creating eMMC snapshot...")
    before = filesystem_snapshot()
    proc_before = process_writes()
    sectors_before = mmc_written_sectors()
    print(f"Files in snapshot: {len(before)}")
    print(f"Measurement duration: {args.duration} s")
    if start_uptime is not None:
        print(f"System uptime at start: {start_uptime:.0f} s")
    time.sleep(args.duration)

    after = filesystem_snapshot()
    proc_after = process_writes()
    sectors_after = mmc_written_sectors()

    modified = [
        (path, before[path], value)
        for path, value in after.items()
        if path in before and before[path] != value
    ]
    created = sorted(path for path in after if path not in before)
    deleted = sorted(path for path in before if path not in after)

    print("\n===== MODIFIED FILES ON EMMC =====")
    if modified:
        for path, old, new in sorted(modified):
            print(path)
            print(f"    size: {old[0]} -> {new[0]}")
            print(f"    mtime_ns: {old[1]} -> {new[1]}")
    else:
        print("NONE")

    print("\n===== CREATED FILES ON EMMC =====")
    print("\n".join(created) if created else "NONE")

    print("\n===== DELETED FILES ON EMMC =====")
    print("\n".join(deleted) if deleted else "NONE")

    print("\n===== PROCESS WRITE_BYTES DELTA =====")
    deltas: list[tuple[int, str, str]] = []
    for key, (after_bytes, cmd) in proc_after.items():
        previous = proc_before.get(key)
        if previous is None:
            continue
        delta = after_bytes - previous[0]
        if delta > 0:
            deltas.append((delta, key[0], cmd))
    if deltas:
        for delta, pid, cmd in sorted(deltas, reverse=True)[: args.top_processes]:
            print(f"{delta:12d} B  PID={pid:>6}  {cmd}")
    else:
        print("NONE")

    print("\n===== MMCBLK0 PHYSICAL WRITES =====")
    if sectors_before is None or sectors_after is None:
        print("unable to read /proc/diskstats")
    else:
        sectors = max(0, sectors_after - sectors_before)
        written = sectors * 512
        mib = written / 1024 / 1024
        per_day = mib * 86400 / args.duration
        print(f"sectors: {sectors}")
        print(f"bytes:   {written}")
        print(f"MiB:     {mib:.3f}")
        print(f"MiB/day equivalent at this activity level: {per_day:.1f}")
        if args.duration < 3600:
            print(
                "NOTE: short-window daily extrapolation is diagnostic only; "
                "it is not an eMMC endurance estimate."
            )
        if start_uptime is not None and start_uptime < 1800:
            print(
                "NOTE: audit started within 30 minutes of boot; filesystem "
                "journal and early-boot service activity can inflate the rate."
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
