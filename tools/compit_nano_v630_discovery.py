#!/usr/bin/env python3
"""Read-only Modbus RTU discovery tool for COMPIT NANO firmware 6.30.

The register map for this firmware is treated as unknown.
The tool only uses FC03 Read Holding Registers and never sends writes.

Examples:
  py tools\compit_nano_v630_discovery.py capture --port COM10 --start 2000 --end 2100 --output nano_idle.csv
  py tools\compit_nano_v630_discovery.py diff --before nano_idle.csv --after nano_bieg1.csv
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError as exc:
    raise SystemExit("Brak pyserial. Zainstaluj: py -m pip install pyserial") from exc

FC03 = 0x03
DEFAULT_PORT = "COM10"
DEFAULT_ADDRESS = 44
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 0.45


class ModbusError(RuntimeError):
    pass


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def append_crc(data: bytes) -> bytes:
    crc = crc16_modbus(data)
    return data + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusError("za krótka ramka")
    received = frame[-2] | (frame[-1] << 8)
    expected = crc16_modbus(frame[:-2])
    if received != expected:
        raise ModbusError(
            f"błędne CRC: odebrane=0x{received:04X}, oczekiwane=0x{expected:04X}"
        )


def read_exact(port: serial.Serial, size: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    result = bytearray()
    while len(result) < size and time.monotonic() < deadline:
        chunk = port.read(size - len(result))
        if chunk:
            result.extend(chunk)
    return bytes(result)


def read_one(port: serial.Serial, slave: int, address: int, timeout: float) -> tuple[int, bytes, bytes]:
    request = append_crc(struct.pack(">BBHH", slave, FC03, address, 1))
    port.reset_input_buffer()
    port.write(request)
    port.flush()

    header = read_exact(port, 3, timeout)
    if len(header) != 3:
        raise ModbusError("brak odpowiedzi")

    rx_slave, function, third = header
    if rx_slave != slave:
        raise ModbusError(f"odpowiedź slave={rx_slave}, oczekiwano {slave}")

    if function == (FC03 | 0x80):
        tail = read_exact(port, 2, timeout)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError("niepełna odpowiedź wyjątkowa")
        verify_crc(frame)
        raise ModbusError(f"wyjątek Modbus 0x{third:02X}")

    if function != FC03 or third != 2:
        raise ModbusError(f"nieoczekiwana odpowiedź FC=0x{function:02X}, bytes={third}")

    tail = read_exact(port, 4, timeout)
    frame = header + tail
    if len(frame) != 7:
        raise ModbusError("niepełna odpowiedź")
    verify_crc(frame)
    value = struct.unpack(">H", frame[3:5])[0]
    return value, request, frame


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def capture(args: argparse.Namespace) -> int:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print("TRYB TYLKO DO ODCZYTU — wyłącznie Modbus FC03.")
    print("Mapa firmware 6.30 jest nieznana; zapisujemy surowe wartości bez nazw.")
    print(
        f"{args.port}, {args.baud} bit/s, 8N1, slave={args.address}, "
        f"adresy {args.start}..{args.end}"
    )

    responses = 0
    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.02,
            write_timeout=args.timeout,
        ) as port, output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("address", "raw_u16", "signed_i16", "div10", "tx_hex", "rx_hex", "status"))

            for address in range(args.start, args.end + 1):
                try:
                    raw, tx, rx = read_one(port, args.address, address, args.timeout)
                    signed = signed16(raw)
                    writer.writerow((
                        address,
                        raw,
                        signed,
                        f"{signed / 10.0:.1f}",
                        tx.hex(" ").upper(),
                        rx.hex(" ").upper(),
                        "OK",
                    ))
                    print(f"ADR {address:5d}: raw={raw:5d} signed={signed:6d} div10={signed / 10.0:8.1f}")
                    responses += 1
                except ModbusError as exc:
                    writer.writerow((address, "", "", "", "", "", str(exc)))
                time.sleep(args.delay)
    except serial.SerialException as exc:
        print(f"BŁĄD portu {args.port}: {exc}", file=sys.stderr)
        return 2

    print(f"\nZapisano {responses} odpowiedzi do {output}")
    return 0 if responses else 1


def load_snapshot(path: str) -> dict[int, int]:
    result: dict[int, int] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") == "OK" and row.get("raw_u16"):
                result[int(row["address"])] = int(row["raw_u16"])
    return result


def diff(args: argparse.Namespace) -> int:
    before = load_snapshot(args.before)
    after = load_snapshot(args.after)
    addresses = sorted(set(before) | set(after))
    changed = 0

    print(f"Porównanie: {args.before} -> {args.after}")
    for address in addresses:
        old = before.get(address)
        new = after.get(address)
        if old == new:
            continue
        changed += 1
        if old is None or new is None:
            print(f"ADR {address:5d}: {old!s:>6} -> {new!s:<6}")
            continue
        delta = signed16(new) - signed16(old)
        print(
            f"ADR {address:5d}: {old:5d} -> {new:5d}  "
            f"delta={delta:+6d}  div10={signed16(old)/10.0:.1f}->{signed16(new)/10.0:.1f}"
        )

    if not changed:
        print("Brak zmian.")
    else:
        print(f"Liczba zmienionych adresów: {changed}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    cap = commands.add_parser("capture", help="Zapisz surowy snapshot rejestrów")
    cap.add_argument("--port", default=DEFAULT_PORT)
    cap.add_argument("--address", type=int, default=DEFAULT_ADDRESS)
    cap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    cap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    cap.add_argument("--start", type=int, default=2000)
    cap.add_argument("--end", type=int, default=2100)
    cap.add_argument("--delay", type=float, default=0.03)
    cap.add_argument("--output", required=True)
    cap.set_defaults(func=capture)

    cmp_parser = commands.add_parser("diff", help="Porównaj dwa snapshoty")
    cmp_parser.add_argument("--before", required=True)
    cmp_parser.add_argument("--after", required=True)
    cmp_parser.set_defaults(func=diff)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "capture":
        if not 1 <= args.address <= 247:
            parser.error("adres slave musi należeć do 1..247")
        if not 0 <= args.start <= args.end <= 65535:
            parser.error("zakres adresów jest nieprawidłowy")
        if args.timeout <= 0 or args.delay < 0:
            parser.error("timeout musi być dodatni, delay nieujemny")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
