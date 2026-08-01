#!/usr/bin/env python3
"""Safe command-line bring-up tool for the DFRobot DFR0971 DAC."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

from gp8403 import GP8403, GP8403Config, GP8403Error


DEFAULT_SEQUENCE = (0.0, 2.0, 5.0, 8.0, 10.0)


def parse_i2c_address(value: str) -> int:
    try:
        address = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Address must be decimal or hexadecimal, e.g. 0x58"
        ) from exc
    if not 0x03 <= address <= 0x77:
        raise argparse.ArgumentTypeError("Address must be a valid 7-bit I2C address")
    return address


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "DFR0971/GP8403 hardware bring-up. "
            "Keep both fan control inputs disconnected."
        )
    )
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number (default: 1)")
    parser.add_argument(
        "--address",
        type=parse_i2c_address,
        default=0x58,
        help="7-bit I2C address (default: 0x58)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("probe", help="Check whether the DAC acknowledges")
    subparsers.add_parser("zero", help="Set both outputs to 0 V")

    measure = subparsers.add_parser(
        "measure",
        help="Set one test voltage, wait for measurement, then return both outputs to 0 V",
    )
    measure.add_argument("--channel", type=int, choices=(0, 1), required=True)
    measure.add_argument("--voltage", type=float, required=True)
    measure.add_argument(
        "--confirm-no-fans",
        action="store_true",
        help="Required acknowledgement that fan inputs are disconnected",
    )

    sequence = subparsers.add_parser(
        "sequence",
        help="Step through 0, 2, 5, 8 and 10 V, then return both outputs to 0 V",
    )
    sequence.add_argument("--channel", type=int, choices=(0, 1), required=True)
    sequence.add_argument(
        "--confirm-no-fans",
        action="store_true",
        help="Required acknowledgement that fan inputs are disconnected",
    )
    return parser


def require_no_fans_confirmation(args: argparse.Namespace) -> None:
    if not args.confirm_no_fans:
        raise GP8403Error(
            "Refusing non-zero output. Disconnect both fan control inputs and "
            "repeat with --confirm-no-fans."
        )


def wait_for_measurement(channel: int, voltage: float) -> None:
    input(
        f"CH{channel} set to {voltage:.3f} V. Measure VOUT{channel} to GND, "
        "then press Enter..."
    )


def run_measurement(dac: GP8403, channel: int, voltage: float) -> None:
    dac.zero_all()
    dac.configure_output_range()
    try:
        dac.set_voltage(channel, voltage)
        wait_for_measurement(channel, voltage)
    finally:
        dac.zero_all()


def run_sequence(dac: GP8403, channel: int, values: Iterable[float]) -> None:
    dac.zero_all()
    dac.configure_output_range()
    try:
        for voltage in values:
            dac.set_voltage(channel, voltage)
            wait_for_measurement(channel, voltage)
    finally:
        dac.zero_all()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = GP8403Config(bus=args.bus, address=args.address, output_range_volts=10.0)

    try:
        with GP8403(config) as dac:
            if args.command == "probe":
                value = dac.probe()
                print(
                    f"GP8403 responded at 0x{args.address:02X} on /dev/i2c-{args.bus}; "
                    f"read byte: 0x{value:02X}"
                )
            elif args.command == "zero":
                dac.configure_output_range()
                dac.zero_all()
                print("Both outputs set to 0 V.")
            elif args.command == "measure":
                require_no_fans_confirmation(args)
                run_measurement(dac, args.channel, args.voltage)
                print("Measurement finished; both outputs returned to 0 V.")
            elif args.command == "sequence":
                require_no_fans_confirmation(args)
                run_sequence(dac, args.channel, DEFAULT_SEQUENCE)
                print("Sequence finished; both outputs returned to 0 V.")
            else:
                parser.error(f"Unsupported command: {args.command}")
    except (GP8403Error, ValueError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
