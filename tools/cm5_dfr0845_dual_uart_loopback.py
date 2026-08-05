#!/usr/bin/env python3
"""Validate two CM5 UARTs and two DFR0845 modules using an RS-485 cross-loop.

Temporary test wiring on the isolated RS-485 sides:

    DFR0845 A  <->  DFR0845 A
    DFR0845 B  <->  DFR0845 B
    DFR0845 GND <-> DFR0845 GND

The script sends deterministic binary frames in both directions and verifies
that the opposite UART receives every byte unchanged. DFR0845 controls the
half-duplex direction automatically, so RTS/CTS must remain disabled.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

try:
    import serial
except ImportError as exc:  # pragma: no cover - hardware utility
    raise SystemExit(
        "Brak biblioteki pyserial. Zainstaluj: sudo apt install python3-serial"
    ) from exc


@dataclass
class DirectionStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port-a", default="/dev/ttyAMA0")
    parser.add_argument("--port-b", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=19200)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument(
        "--turnaround-delay",
        type=float,
        default=0.020,
        help="Cisza między zmianą kierunku transmisji w sekundach",
    )
    return parser.parse_args()


def make_payload(direction: bytes, sequence: int) -> bytes:
    return b"WVC-DFR0845-" + direction + b"-" + sequence.to_bytes(4, "big") + b"\x55\xaa\x00\xff"


def read_exact(port: serial.Serial, expected_size: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    received = bytearray()
    while len(received) < expected_size and time.monotonic() < deadline:
        chunk = port.read(expected_size - len(received))
        if chunk:
            received.extend(chunk)
    return bytes(received)


def transfer(
    source: serial.Serial,
    destination: serial.Serial,
    payload: bytes,
    timeout: float,
) -> tuple[bool, bytes]:
    source.reset_input_buffer()
    destination.reset_input_buffer()
    source.reset_output_buffer()

    written = source.write(payload)
    source.flush()
    if written != len(payload):
        return False, b""

    received = read_exact(destination, len(payload), timeout)
    return received == payload, received


def print_failure(label: str, expected: bytes, received: bytes) -> None:
    print(
        f"BŁĄD {label}: expected={expected.hex(' ')} received={received.hex(' ')}",
        file=sys.stderr,
    )


def main() -> int:
    args = parse_args()
    if args.baud <= 0:
        raise SystemExit("Baud musi być dodatni")
    if args.iterations <= 0:
        raise SystemExit("Iterations musi być dodatnie")
    if args.timeout <= 0:
        raise SystemExit("Timeout musi być dodatni")
    if args.turnaround_delay < 0:
        raise SystemExit("Turnaround delay nie może być ujemny")
    if args.port_a == args.port_b:
        raise SystemExit("Port A i port B muszą być różne")

    stats_a_to_b = DirectionStats()
    stats_b_to_a = DirectionStats()

    serial_settings = dict(
        baudrate=args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.05,
        write_timeout=args.timeout,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    print(
        f"Test {args.port_a} <-> {args.port_b}, {args.baud} bit/s, "
        f"8N1, iterations={args.iterations}"
    )

    try:
        with serial.Serial(args.port_a, **serial_settings) as port_a, serial.Serial(
            args.port_b, **serial_settings
        ) as port_b:
            for sequence in range(1, args.iterations + 1):
                payload_a_to_b = make_payload(b"A2B", sequence)
                stats_a_to_b.attempts += 1
                ok, received = transfer(port_a, port_b, payload_a_to_b, args.timeout)
                if ok:
                    stats_a_to_b.successes += 1
                else:
                    stats_a_to_b.failures += 1
                    print_failure("A->B", payload_a_to_b, received)

                time.sleep(args.turnaround_delay)

                payload_b_to_a = make_payload(b"B2A", sequence)
                stats_b_to_a.attempts += 1
                ok, received = transfer(port_b, port_a, payload_b_to_a, args.timeout)
                if ok:
                    stats_b_to_a.successes += 1
                else:
                    stats_b_to_a.failures += 1
                    print_failure("B->A", payload_b_to_a, received)

                if sequence % 10 == 0 or sequence == args.iterations:
                    print(
                        f"progress={sequence}/{args.iterations} "
                        f"A->B={stats_a_to_b.successes}/{stats_a_to_b.attempts} "
                        f"B->A={stats_b_to_a.successes}/{stats_b_to_a.attempts}"
                    )

                if sequence < args.iterations:
                    time.sleep(args.turnaround_delay)
    except serial.SerialException as exc:
        print(f"Błąd portu szeregowego: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Test przerwany przez użytkownika", file=sys.stderr)
        return 130

    print("\nPODSUMOWANIE")
    print(
        f"A->B attempts={stats_a_to_b.attempts} successes={stats_a_to_b.successes} "
        f"failures={stats_a_to_b.failures}"
    )
    print(
        f"B->A attempts={stats_b_to_a.attempts} successes={stats_b_to_a.successes} "
        f"failures={stats_b_to_a.failures}"
    )

    return 0 if stats_a_to_b.failures == 0 and stats_b_to_a.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
