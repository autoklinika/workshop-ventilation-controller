#!/usr/bin/env python3
"""Poll multiple KAmod + SEN55 Modbus nodes without one failure blocking another."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

try:
    import serial
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Brak biblioteki pyserial. Zainstaluj: py -m pip install pyserial"
    ) from exc

from read_modbus_sensor import (
    ModbusError,
    decode,
    print_decoded,
    read_input_registers,
)

EXPECTED_MAP_VERSION = 1


@dataclass
class NodeStats:
    polls: int = 0
    successes: int = 0
    timeouts_or_protocol_errors: int = 0
    invalid_measurements: int = 0
    stale_measurements: int = 0
    map_version_errors: int = 0


def parse_addresses(value: str) -> list[int]:
    addresses: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        address = int(item, 10)
        if not 1 <= address <= 247:
            raise argparse.ArgumentTypeError("Każdy adres musi należeć do zakresu 1..247")
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise argparse.ArgumentTypeError("Podaj co najmniej jeden adres")
    return addresses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Port izolowanego USB-RS485, np. COM10")
    parser.add_argument("--addresses", type=parse_addresses, default=[1, 2])
    parser.add_argument("--baud", type=int, default=19200)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--cycles", type=int, default=0, help="0 oznacza pracę ciągłą")
    return parser.parse_args()


def print_summary(stats: dict[int, NodeStats]) -> None:
    print("\nPODSUMOWANIE STAGE 2B")
    for address, value in stats.items():
        print(
            f"slave={address}: polls={value.polls} success={value.successes} "
            f"errors={value.timeouts_or_protocol_errors} invalid={value.invalid_measurements} "
            f"stale={value.stale_measurements} map_errors={value.map_version_errors}"
        )


def main() -> int:
    args = parse_args()
    if args.timeout <= 0 or args.interval <= 0:
        raise SystemExit("Timeout i interval muszą być dodatnie")
    if args.cycles < 0:
        raise SystemExit("Liczba cykli nie może być ujemna")

    stats = {address: NodeStats() for address in args.addresses}
    cycle = 0

    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=args.timeout,
            write_timeout=args.timeout,
        ) as port:
            while args.cycles == 0 or cycle < args.cycles:
                cycle += 1
                print(f"\n=== cykl {cycle} ===")
                for address in args.addresses:
                    node = stats[address]
                    node.polls += 1
                    print(f"[slave {address}]")
                    try:
                        decoded = decode(read_input_registers(port, address))
                        node.successes += 1
                        if decoded.map_version != EXPECTED_MAP_VERSION:
                            node.map_version_errors += 1
                            print(
                                f"BŁĄD MAPY: odebrano {decoded.map_version}, "
                                f"oczekiwano {EXPECTED_MAP_VERSION}",
                                file=sys.stderr,
                            )
                        if "measurement_valid" not in decoded.status:
                            node.invalid_measurements += 1
                            print("UWAGA: MEASUREMENT_VALID nie jest ustawiony")
                        if "measurement_stale" in decoded.status:
                            node.stale_measurements += 1
                            print("UWAGA: pomiar jest nieaktualny")
                        print_decoded(decoded)
                    except ModbusError as exc:
                        node.timeouts_or_protocol_errors += 1
                        print(f"BŁĄD slave {address}: {exc}", file=sys.stderr)
                if args.cycles == 0 or cycle < args.cycles:
                    time.sleep(args.interval)
    except serial.SerialException as exc:
        print(f"Nie można użyć portu {args.port}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    finally:
        print_summary(stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
