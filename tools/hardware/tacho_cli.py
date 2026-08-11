#!/usr/bin/env python3
"""Read-only CM5 EC-fan TACHO diagnostic using libgpiod 2.x.

The tool intentionally stays outside ventilation-core runtime integration. It is
for hardware validation of the two TACHO inputs only.

Current project wiring under validation:

    TACHO_INPUT_1 -> GPIO17 / physical pin 11
    TACHO_INPUT_2 -> GPIO27 / physical pin 13

For the current one-fan laboratory setup the physical fan is controlled by
EXTRACT / DAC CH1 / VOUT1. After moving its TACHO lead to GPIO27 use
``--only extract`` so the diagnostic requests only GPIO27 and reports one
unambiguous channel.

Each line is externally conditioned with 10 kOhm pull-up to 3.3 V, 1 kOhm
series resistance and 1 nF to GND. Therefore the GPIO request explicitly
disables the SoC internal bias and listens only for rising edges.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from pathlib import Path
from types import ModuleType

from ventilation_core.domain.tacho import TachoEstimator, TachoReading


DEFAULT_SUPPLY_LINE = "GPIO17"
DEFAULT_EXTRACT_LINE = "GPIO27"
DEFAULT_DURATION_SECONDS = 10.0
DEFAULT_PRINT_INTERVAL_SECONDS = 1.0


class TachoDiagnosticError(RuntimeError):
    """Raised when the read-only GPIO diagnostic cannot be started safely."""


def load_gpiod() -> ModuleType:
    try:
        import gpiod  # type: ignore[import-not-found]
    except ImportError as exc:
        raise TachoDiagnosticError(
            "Python libgpiod bindings are missing. On Raspberry Pi OS / Debian 13 "
            "install packages: sudo apt install gpiod python3-libgpiod"
        ) from exc
    return gpiod


def gpiochip_paths() -> tuple[str, ...]:
    paths = sorted(glob.glob("/dev/gpiochip*"))
    unique: list[str] = []
    seen_devices: set[int] = set()
    for path in paths:
        try:
            device_id = os.stat(path).st_rdev
        except OSError:
            continue
        if device_id in seen_devices:
            continue
        seen_devices.add(device_id)
        unique.append(path)
    return tuple(unique)


def resolve_chip_and_offsets(
    gpiod: ModuleType,
    line_ids: tuple[str, ...],
    *,
    requested_chip: str | None = None,
) -> tuple[str, tuple[int, ...]]:
    if not line_ids:
        raise TachoDiagnosticError("At least one GPIO line must be requested")

    paths = (requested_chip,) if requested_chip else gpiochip_paths()
    if not paths:
        raise TachoDiagnosticError("No /dev/gpiochip* devices found")

    matches: list[tuple[str, tuple[int, ...]]] = []
    errors: list[str] = []
    for path in paths:
        if path is None:
            continue
        try:
            with gpiod.Chip(path) as chip:
                offsets = tuple(int(chip.line_offset_from_id(line)) for line in line_ids)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        matches.append((path, offsets))

    if not matches:
        detail = "; ".join(errors) if errors else "requested lines not found"
        lines_text = ", ".join(line_ids)
        raise TachoDiagnosticError(
            f"Could not find one GPIO chip containing {lines_text}: {detail}"
        )
    if len(matches) > 1 and requested_chip is None:
        paths_text = ", ".join(match[0] for match in matches)
        raise TachoDiagnosticError(
            f"GPIO line names are ambiguous across chips ({paths_text}); rerun with --chip PATH"
        )
    return matches[0]


def format_reading(name: str, reading: TachoReading) -> str:
    if not reading.valid:
        age = "n/a" if reading.age_seconds is None else f"{reading.age_seconds:.3f}s"
        return f"{name:<7}  NO VALID TACHO  age={age}"
    return (
        f"{name:<7}  {reading.frequency_hz:8.3f} Hz  "
        f"{reading.rpm:8.1f} RPM  samples={reading.sample_count:2d}  "
        f"age={reading.age_seconds:.3f}s"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only validation of EC-fan TACHO inputs on CM5 using libgpiod 2.x"
        )
    )
    parser.add_argument(
        "--chip",
        help=(
            "GPIO chip path, e.g. /dev/gpiochip0. Default: auto-detect one chip "
            "containing the requested named line(s)."
        ),
    )
    parser.add_argument("--supply-line", default=DEFAULT_SUPPLY_LINE)
    parser.add_argument("--extract-line", default=DEFAULT_EXTRACT_LINE)
    parser.add_argument(
        "--only",
        choices=("supply", "extract"),
        help=(
            "Request and report only one channel. For the current one-fan lab setup, "
            "after moving the fan TACHO to GPIO27 use --only extract."
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help=f"Measurement duration in seconds (default: {DEFAULT_DURATION_SECONDS:g})",
    )
    parser.add_argument(
        "--print-interval",
        type=float,
        default=DEFAULT_PRINT_INTERVAL_SECONDS,
        help=f"Status print interval in seconds (default: {DEFAULT_PRINT_INTERVAL_SECONDS:g})",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.duration <= 0.0:
        raise TachoDiagnosticError("--duration must be positive")
    if args.print_interval <= 0.0:
        raise TachoDiagnosticError("--print-interval must be positive")
    if args.supply_line == args.extract_line:
        raise TachoDiagnosticError("Supply and extract TACHO must use two different GPIO lines")
    if args.chip is not None and not Path(args.chip).exists():
        raise TachoDiagnosticError(f"GPIO chip does not exist: {args.chip}")


def selected_channels(args: argparse.Namespace) -> tuple[tuple[str, str], ...]:
    if args.only == "supply":
        return (("SUPPLY", args.supply_line),)
    if args.only == "extract":
        return (("EXTRACT", args.extract_line),)
    return (("SUPPLY", args.supply_line), ("EXTRACT", args.extract_line))


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    gpiod = load_gpiod()
    channels = selected_channels(args)
    line_ids = tuple(line_id for _, line_id in channels)
    chip_path, offsets = resolve_chip_and_offsets(
        gpiod,
        line_ids,
        requested_chip=args.chip,
    )

    channel_offsets = {
        name: (line_id, offset)
        for (name, line_id), offset in zip(channels, offsets, strict=True)
    }

    print("CM5 TACHO read-only diagnostic")
    print(f"chip:    {chip_path}")
    for name, (line_id, offset) in channel_offsets.items():
        print(f"{name + ':':<9}{line_id} -> offset {offset}")
    print("edge:    rising")
    print("bias:    disabled (external 10 kOhm pull-up is required)")
    print("formula: RPM = TACHO_HZ * 20 (3 pulses/revolution)")
    print()

    settings = gpiod.LineSettings(
        direction=gpiod.line.Direction.INPUT,
        edge_detection=gpiod.line.Edge.RISING,
        bias=gpiod.line.Bias.DISABLED,
        event_clock=gpiod.line.Clock.MONOTONIC,
    )

    estimators = {
        offset: TachoEstimator()
        for _, offset in channel_offsets.values()
    }
    names = {
        offset: name
        for name, (_, offset) in channel_offsets.items()
    }

    start = time.monotonic()
    deadline = start + args.duration
    next_print = start + min(args.print_interval, args.duration)

    try:
        requested_offsets = tuple(estimators)
        with gpiod.request_lines(
            chip_path,
            consumer="wvc-tacho-diagnostic",
            config={requested_offsets: settings},
            event_buffer_size=64,
        ) as request:
            while True:
                now = time.monotonic()
                if now >= deadline:
                    break

                wait_seconds = min(0.1, deadline - now, max(0.0, next_print - now))
                if request.wait_edge_events(wait_seconds):
                    for event in request.read_edge_events():
                        estimator = estimators.get(event.line_offset)
                        if estimator is None:
                            continue
                        estimator.add_edge(event.timestamp_ns / 1_000_000_000.0)

                now = time.monotonic()
                if now >= next_print or now >= deadline:
                    for offset in requested_offsets:
                        print(format_reading(names[offset], estimators[offset].read(now)))
                    print()
                    next_print += args.print_interval
    except OSError as exc:
        raise TachoDiagnosticError(
            f"Cannot request/read TACHO GPIO lines on {chip_path}: {exc}. "
            "Check gpioinfo, line ownership and device permissions."
        ) from exc

    now = time.monotonic()
    print("FINAL")
    for offset in requested_offsets:
        print(format_reading(names[offset], estimators[offset].read(now)))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (TachoDiagnosticError, ValueError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
