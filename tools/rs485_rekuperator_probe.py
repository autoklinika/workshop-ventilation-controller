#!/usr/bin/env python3
"""Windows RS-485 discovery tool for the workshop recuperator.

Modes:
  ports     list serial ports
  discover  passive baud/format discovery; transmits nothing
  probe     active Modbus RTU scan using read-only FC03/FC04 only
  listen    continuous raw capture for known serial parameters

Dependency:
  py -m pip install pyserial
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit(
        "Brak biblioteki pyserial. Zainstaluj: py -m pip install pyserial"
    ) from exc

COMMON_BAUDS = (2400, 4800, 9600, 19200, 38400, 57600, 115200)
COMMON_FORMATS = ("8N1", "8E1")
COMMON_ADDRESSES = (1, 2, 3, 4, 5, 10, 16, 20, 30, 31, 32, 100, 247)
READ_FUNCTIONS = (0x03, 0x04)


@dataclass(frozen=True)
class Profile:
    baud: int
    bits: int
    parity: str
    stops: int

    @property
    def label(self) -> str:
        return f"{self.bits}{self.parity}{self.stops}"

    @property
    def char_time(self) -> float:
        return (1 + self.bits + (0 if self.parity == "N" else 1) + self.stops) / self.baud


@dataclass(frozen=True)
class Frame:
    timestamp: float
    data: bytes

    @property
    def crc_ok(self) -> bool:
        return valid_crc(self.data)


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def add_crc(data: bytes) -> bytes:
    value = crc16(data)
    return data + bytes((value & 0xFF, value >> 8))


def valid_crc(frame: bytes) -> bool:
    return len(frame) >= 4 and (frame[-2] | frame[-1] << 8) == crc16(frame[:-2])


def parse_profile(baud: int, text: str) -> Profile:
    value = text.upper()
    if len(value) != 3 or value[0] not in "78" or value[1] not in "NEO" or value[2] not in "12":
        raise argparse.ArgumentTypeError("Format musi mieć postać 8N1, 8E1, 8O1 lub 8N2")
    return Profile(baud, int(value[0]), value[1], int(value[2]))


def profiles(bauds: Sequence[int], formats: Sequence[str]) -> list[Profile]:
    return [parse_profile(baud, fmt) for baud in bauds for fmt in formats]


def open_port(name: str, profile: Profile) -> serial.Serial:
    return serial.Serial(
        port=name,
        baudrate=profile.baud,
        bytesize={7: serial.SEVENBITS, 8: serial.EIGHTBITS}[profile.bits],
        parity={"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}[profile.parity],
        stopbits={1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO}[profile.stops],
        timeout=0.01,
        write_timeout=0.5,
    )


def frame_gap(profile: Profile) -> float:
    return max(profile.char_time * 4.0, 0.004)


def collect(port: serial.Serial, profile: Profile, duration: float) -> list[Frame]:
    end = time.monotonic() + duration
    gap = frame_gap(profile)
    result: list[Frame] = []
    buffer = bytearray()
    started = 0.0
    last_byte = 0.0
    port.reset_input_buffer()

    while time.monotonic() < end:
        chunk = port.read(max(1, port.in_waiting))
        now = time.monotonic()
        if chunk:
            if not buffer:
                started = time.time()
            buffer.extend(chunk)
            last_byte = now
        elif buffer and now - last_byte >= gap:
            result.append(Frame(started, bytes(buffer)))
            buffer.clear()

    if buffer:
        result.append(Frame(started, bytes(buffer)))
    return result


def receive(port: serial.Serial, profile: Profile, timeout: float) -> bytes:
    end = time.monotonic() + timeout
    gap = frame_gap(profile)
    buffer = bytearray()
    last_byte = 0.0
    while time.monotonic() < end:
        chunk = port.read(max(1, port.in_waiting))
        now = time.monotonic()
        if chunk:
            buffer.extend(chunk)
            last_byte = now
        elif buffer and now - last_byte >= gap:
            break
    return bytes(buffer)


def request(address: int, function: int) -> bytes:
    return add_crc(bytes((address, function, 0, 0, 0, 1)))


def decode(frame: bytes) -> str:
    if not valid_crc(frame):
        return "brak prawidłowego CRC Modbus"
    address, function = frame[0], frame[1]
    if function & 0x80:
        names = {
            1: "Illegal Function",
            2: "Illegal Data Address",
            3: "Illegal Data Value",
            4: "Slave Device Failure",
            6: "Slave Device Busy",
        }
        code = frame[2]
        return f"Modbus: address={address}, exception FC=0x{function & 0x7F:02X}, code=0x{code:02X} ({names.get(code, 'unknown')})"
    if function in READ_FUNCTIONS and len(frame) >= 7:
        count = frame[2]
        if len(frame) == 3 + count + 2 and count % 2 == 0:
            values = [
                (frame[i] << 8) | frame[i + 1]
                for i in range(3, 3 + count, 2)
            ]
            return f"Modbus: address={address}, FC=0x{function:02X}, registers={values}"
    return f"Modbus: address={address}, FC=0x{function:02X}, length={len(frame)}"


def parse_addresses(text: str) -> list[int]:
    result: set[int] = set()
    for item in text.split(","):
        token = item.strip()
        if not token:
            continue
        if "-" in token:
            first, last = map(int, token.split("-", 1))
            result.update(range(min(first, last), max(first, last) + 1))
        else:
            result.add(int(token))
    if not result or any(not 1 <= value <= 247 for value in result):
        raise argparse.ArgumentTypeError("Adresy Modbus muszą należeć do zakresu 1-247")
    return sorted(result)


def log_open(path: str | None):
    if not path:
        return None, None
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = output.open("w", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    writer.writerow(("timestamp", "mode", "baud", "format", "direction", "hex", "crc_ok", "description"))
    return handle, writer


def log_row(writer, mode: str, profile: Profile, direction: str, data: bytes, description: str) -> None:
    if writer is not None:
        writer.writerow((
            datetime.now().isoformat(timespec="milliseconds"),
            mode,
            profile.baud,
            profile.label,
            direction,
            data.hex(" ").upper(),
            int(valid_crc(data)),
            description,
        ))


def cmd_ports(_: argparse.Namespace) -> int:
    found = list(list_ports.comports())
    if not found:
        print("Nie znaleziono portów COM.")
        return 1
    for item in found:
        print(f"{item.device}: {item.description} [{item.hwid}]")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    handle, writer = log_open(args.log)
    print("Pasywny nasłuch: skrypt niczego nie wysyła.")
    print("Oryginalny sterownik rekuperatora musi pozostać podłączony i aktywny.")
    try:
        for profile in profiles(args.baud, args.format):
            print(f"\n{profile.baud} bit/s, {profile.label}, nasłuch {args.seconds:.1f} s...")
            try:
                with open_port(args.port, profile) as port:
                    frames = collect(port, profile, args.seconds)
            except serial.SerialException as exc:
                print(f"BŁĄD portu {args.port}: {exc}", file=sys.stderr)
                return 2
            if not frames:
                print("  brak danych")
                continue
            for frame in frames:
                description = decode(frame.data)
                print(f"  RX {frame.data.hex(' ').upper()} | {'CRC OK' if frame.crc_ok else 'CRC ?'} | {description}")
                log_row(writer, "discover", profile, "RX", frame.data, description)
            if any(frame.crc_ok for frame in frames):
                print(f"\nWYKRYTO prawdopodobny Modbus RTU: {profile.baud} bit/s, {profile.label}")
                print(
                    f"py tools\\rs485_rekuperator_probe.py listen --port {args.port} "
                    f"--baud {profile.baud} --format {profile.label} --log rekuperator_frames.csv"
                )
                return 0
    finally:
        if handle:
            handle.close()

    print("\nNie wykryto ramek z prawidłowym CRC Modbus.")
    print("Gdy rekuperator jest samym slave bez sterownika, uruchom tryb probe.")
    return 1


def cmd_probe(args: argparse.Namespace) -> int:
    addresses = list(range(1, 248)) if args.all_addresses else args.addresses
    handle, writer = log_open(args.log)
    print("Aktywny skan read-only: wysyłane są wyłącznie FC03 i FC04. Brak zapisów.")
    try:
        for profile in profiles(args.baud, args.format):
            print(f"\nSkan {profile.baud} bit/s, {profile.label}")
            try:
                with open_port(args.port, profile) as port:
                    for address in addresses:
                        for function in READ_FUNCTIONS:
                            tx = request(address, function)
                            port.reset_input_buffer()
                            port.write(tx)
                            port.flush()
                            rx = receive(port, profile, args.timeout)
                            if rx.startswith(tx) and len(rx) > len(tx):
                                rx = rx[len(tx):]
                            log_row(writer, "probe", profile, "TX", tx, f"address={address} FC=0x{function:02X}")
                            if not rx:
                                continue
                            description = decode(rx)
                            log_row(writer, "probe", profile, "RX", rx, description)
                            if valid_crc(rx) and rx[0] == address:
                                print("\nWYKRYTO ODPOWIEDŹ")
                                print(f"  parametry: {profile.baud} bit/s, {profile.label}")
                                print(f"  address: {address}")
                                print(f"  TX: {tx.hex(' ').upper()}")
                                print(f"  RX: {rx.hex(' ').upper()}")
                                print(f"  {description}")
                                return 0
                        if args.progress and address % 10 == 0:
                            print(f"  sprawdzono do adresu {address}")
            except serial.SerialException as exc:
                print(f"BŁĄD portu {args.port}: {exc}", file=sys.stderr)
                return 2
    finally:
        if handle:
            handle.close()

    print("\nBrak prawidłowej odpowiedzi Modbus RTU.")
    print("Sprawdź A/B, zasilanie, pełny zakres --all-addresses albo pasywny nasłuch z oryginalnym sterownikiem.")
    return 1


def cmd_listen(args: argparse.Namespace) -> int:
    profile = parse_profile(args.baud, args.format)
    handle, writer = log_open(args.log)
    print(f"Nasłuch: {args.port}, {profile.baud}, {profile.label}. Zakończenie: Ctrl+C")
    try:
        with open_port(args.port, profile) as port:
            while True:
                for frame in collect(port, profile, args.window):
                    description = decode(frame.data)
                    stamp = datetime.fromtimestamp(frame.timestamp).isoformat(timespec="milliseconds")
                    print(f"{stamp} RX {frame.data.hex(' ').upper()} | {'CRC OK' if frame.crc_ok else 'CRC ?'} | {description}")
                    log_row(writer, "listen", profile, "RX", frame.data, description)
                if handle:
                    handle.flush()
    except KeyboardInterrupt:
        return 0
    except serial.SerialException as exc:
        print(f"BŁĄD portu {args.port}: {exc}", file=sys.stderr)
        return 2
    finally:
        if handle:
            handle.close()


def add_scan_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", required=True, help="Port KAmod USB RS485 ISO, np. COM10")
    parser.add_argument("--baud", type=int, action="append", help="Można podać wielokrotnie")
    parser.add_argument("--format", action="append", help="Np. 8N1 lub 8E1; można podać wielokrotnie")
    parser.add_argument("--log", help="Opcjonalny plik CSV")


def parser_build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    ports = commands.add_parser("ports")
    ports.set_defaults(func=cmd_ports)

    discover = commands.add_parser("discover")
    add_scan_options(discover)
    discover.add_argument("--seconds", type=float, default=3.0)
    discover.set_defaults(func=cmd_discover)

    probe = commands.add_parser("probe")
    add_scan_options(probe)
    probe.add_argument("--addresses", type=parse_addresses, default=list(COMMON_ADDRESSES))
    probe.add_argument("--all-addresses", action="store_true")
    probe.add_argument("--timeout", type=float, default=0.12)
    probe.add_argument("--progress", action="store_true")
    probe.set_defaults(func=cmd_probe)

    listen = commands.add_parser("listen")
    listen.add_argument("--port", required=True)
    listen.add_argument("--baud", type=int, required=True)
    listen.add_argument("--format", default="8N1")
    listen.add_argument("--window", type=float, default=1.0)
    listen.add_argument("--log")
    listen.set_defaults(func=cmd_listen)
    return parser


def main() -> int:
    parser = parser_build()
    args = parser.parse_args()
    if hasattr(args, "baud") and args.baud is None:
        args.baud = list(COMMON_BAUDS)
    if hasattr(args, "format") and args.format is None:
        args.format = list(COMMON_FORMATS)
    for name in ("seconds", "timeout", "window"):
        if hasattr(args, name) and getattr(args, name) <= 0:
            parser.error(f"--{name} musi być dodatnie")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
