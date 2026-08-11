#!/usr/bin/env python3
"""Read-only CM5 EC-fan TACHO diagnostic using libgpiod 2.x.

The tool intentionally stays outside ventilation-core runtime integration.  It is
for the first hardware validation of the two TACHO inputs only.

Expected project wiring:

    SUPPLY  TACHO -> GPIO17 / physical pin 11
    EXTRACT TACHO -> GPIO27 / physical pin 13

Each line is externally conditioned with 10 kOhm pull-up to 3.3 V, 1 kOhm
series resistance and 1 nF to GND.  Therefore the GPIO request explicitly
disables the SoC internal bias and listens only for rising edges.
"""

from __future__ import annotations

import argparse
import glob
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
    return tuple(sorted(glob.glob("/dev/gpiochip*")))


def resolve_chip_and_offsets(
    gpiod: ModuleType,
    line_ids: tuple[str, str],
    *,
    requested_chip: str | None = None,
) -> tuple[str, tuple[int, int]]:
    paths = (requested_chip,) if requested_chip else gpiochip_paths()
    if not paths:
        raise TachoDiagnosticError("No /dev/gpiochip* devices found")

    matches: list[tuple[str, tuple[int, int]]] = []
    errors: list[str] = []
    for path in paths:
        if path is None:
            continue
        try:
            with gpiod.Chip(path) as chip:
                offsets = tuple(chip.line_offset_from_id(line) for line in line_ids)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        matches.append((path, (int(offsets[0]), int(offsets[1]))))

    if not matches:
        detail = "; ".join(errors) if errors else "requested lines not found"
        raise TachoDiagnosticError(
            f"Could not find one GPIO chip containing {line_ids[0]} and {line_ids[1]}: {detail}"
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
            "Read-only validation of the two EC-fan TACHO inputs on CM5 using libgpiod 2.x"
        )
    )
    parser.add_argument(
        "--chip",
        help=(
            "GPIO chip path, e.g. /dev/gpiochip0. Default: auto-detect one chip "
            "containing both named lines."
        ),
    )
    parser.add_argument("--supply-line", default=DEFAULT_SUPPLY_LINE)
    parser.add_argument("--extract-line", default=DEFAULT_EXTRACT_LINE)
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


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    gpiod = load_gpiod()
    line_ids = (args.supply_line, args.extract_line)
    chip_path, offsets = resolve_chip_and_offsets(
        gpiod,
        line_ids,
        requested_chip=args.chip,
    )
    supply_offset, extract_offset = offsets

    print("CM5 TACHO read-only diagnostic")
    print(f"chip:    {chip_path}")
    print(f"SUPPLY:  {args.supply_line} -> offset {supply_offset}")
    print(f"EXTRACT: {args.extract_line} -> offset {extract_offset}")
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
        supply_offset: TachoEstimator(),
        extract_offset: TachoEstimator(),
    }
    names = {
        supply_offset: "SUPPLY",
        extract_offset: "EXTRACT",
    }

    start = time.monotonic()
    deadline = start + args.duration
    next_print = start + min(args.print_interval, args.duration)

    try:
        with gpiod.request_lines(
            chip_path,
            consumer="wvc-tacho-diagnostic",
            config={(supply_offset, extract_offset): settings},
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
                    print(format_reading("SUPPLY", estimators[supply_offset].read(now)))
                    print(format_reading("EXTRACT", estimators[extract_offset].read(now)))
                    print()
                    next_print += args.print_interval
    except OSError as exc:
        raise TachoDiagnosticError(
            f"Cannot request/read TACHO GPIO lines on {chip_path}: {exc}. "
            "Check gpioinfo, line ownership and device permissions."
        ) from exc

    now = time.monotonic()
    print("FINAL")
    print(format_reading("SUPPLY", estimators[supply_offset].read(now)))
    print(format_reading("EXTRACT", estimators[extract_offset].read(now)))
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
