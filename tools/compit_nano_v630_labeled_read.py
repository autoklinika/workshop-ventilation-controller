#!/usr/bin/env python3
"""Read-only labeled snapshot for COMPIT NANO COLOR 2 firmware 6.30.

Confirmed labels come from direct comparison with the local panel.
Provisional labels are only working hypotheses and MUST NOT be used for writes.
The tool sends only FC03 Read Holding Registers.

Example:
    py tools/compit_nano_v630_labeled_read.py --port COM10 --show-frames
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import serial
except ImportError as exc:
    raise SystemExit("Brak pyserial. Zainstaluj: py -m pip install pyserial") from exc


FC03 = 0x03
DEFAULT_PORT = "COM10"
DEFAULT_ADDRESS = 44
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 0.6


@dataclass(frozen=True)
class RegisterDefinition:
    address: int
    description: str
    display: str = "raw"
    confidence: str = "HIPOTEZA"


# POTWIERDZONE: zweryfikowane przez użytkownika względem ekranu panelu.
# HIPOTEZA: nazwa robocza z wcześniejszych materiałów; nie używać do zapisów.
REGISTERS: dict[int, RegisterDefinition] = {
    2016: RegisterDefinition(2016, "wilgotność", "humidity", "POTWIERDZONE"),
    2021: RegisterDefinition(2021, "temperatura nawiewu", "temperature", "POTWIERDZONE"),
    2022: RegisterDefinition(2022, "temperatura wywiewu", "temperature", "POTWIERDZONE"),
    2023: RegisterDefinition(2023, "temperatura czerpni", "temperature", "POTWIERDZONE"),
    2024: RegisterDefinition(2024, "temperatura wyrzutni", "temperature"),
    2025: RegisterDefinition(2025, "stan presostatu", "bool"),
    2026: RegisterDefinition(2026, "aktywne rozmrażanie", "bool"),
    2027: RegisterDefinition(2027, "praca nagrzewnicy wtórnej", "bool"),
    2028: RegisterDefinition(2028, "aktywne wietrzenie", "bool"),
    2029: RegisterDefinition(2029, "praca nagrzewnicy wstępnej", "bool"),
    2030: RegisterDefinition(2030, "praca chłodnicy", "bool"),
    2031: RegisterDefinition(2031, "zabrudzony filtr", "bool"),
    2032: RegisterDefinition(2032, "moc nagrzewnicy wstępnej", "percent"),
    2033: RegisterDefinition(2033, "moc wentylatora 1", "percent", "POTWIERDZONE"),
    2034: RegisterDefinition(2034, "moc wentylatora 2", "percent", "POTWIERDZONE"),
    2035: RegisterDefinition(2035, "nieznany kod stanu 2035", "raw"),
    2036: RegisterDefinition(2036, "aktualny bieg wentylacji", "raw"),
    2037: RegisterDefinition(2037, "stan bypassu", "raw"),
    2038: RegisterDefinition(2038, "stan GWC", "raw"),
    2039: RegisterDefinition(2039, "podłączony moduł wentylacji", "raw"),
    2040: RegisterDefinition(2040, "alarm AERO / parametr zależny od biegu", "raw"),
    2041: RegisterDefinition(2041, "aktualne obroty AO3", "percent"),
    2042: RegisterDefinition(2042, "nieznany parametr stanu 2042", "raw"),
    2043: RegisterDefinition(2043, "nieznany parametr stanu 2043", "raw"),
    2044: RegisterDefinition(2044, "nieznany parametr stanu 2044", "raw"),
    2045: RegisterDefinition(2045, "nieznany parametr stanu 2045", "raw"),
    2046: RegisterDefinition(2046, "nieznany parametr stanu 2046", "raw"),
    2047: RegisterDefinition(2047, "nieznany parametr stanu 2047", "raw"),
    2048: RegisterDefinition(2048, "nieznany parametr stanu 2048", "raw"),
    2049: RegisterDefinition(2049, "nieznany parametr stanu 2049", "raw"),
    2050: RegisterDefinition(2050, "nieznany parametr stanu 2050", "raw"),
    2051: RegisterDefinition(2051, "nieznany parametr zależny od biegu", "raw"),
    2052: RegisterDefinition(2052, "nieznany parametr stanu 2052", "raw"),
    2053: RegisterDefinition(2053, "nieznany parametr stanu 2053", "raw"),
    2054: RegisterDefinition(2054, "nieznany parametr stanu 2054", "raw"),
    2055: RegisterDefinition(2055, "nieznany parametr stanu 2055", "raw"),
}


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


def read_register(
    port: serial.Serial,
    slave: int,
    address: int,
    timeout: float,
) -> tuple[int, bytes, bytes]:
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
    return struct.unpack(">H", frame[3:5])[0], request, frame


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def display_value(definition: RegisterDefinition, raw: int) -> str:
    signed = signed16(raw)
    if definition.display == "temperature":
        return f"{signed / 10.0:.1f} °C"
    if definition.display == "humidity":
        return f"{raw / 10.0:.1f} %"
    if definition.display == "percent":
        return f"{raw} %"
    if definition.display == "bool":
        return f"{'tak' if raw else 'nie'} ({raw})"
    return str(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--address", type=int, default=DEFAULT_ADDRESS)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=2055)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--show-frames", action="store_true")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--output", default="nano_v630_labeled.csv")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.address <= 247:
        raise SystemExit("Adres slave musi należeć do zakresu 1..247")
    if not 0 <= args.start <= args.end <= 65535:
        raise SystemExit("Nieprawidłowy zakres adresów")
    if args.timeout <= 0 or args.delay < 0 or args.interval <= 0:
        raise SystemExit("Timeout i interval muszą być dodatnie; delay nieujemny")


def run_cycle(port: serial.Serial, args: argparse.Namespace, writer) -> bool:
    print(
        f"\nCOMPIT NANO COLOR 2 v6.30: {args.port}, {args.baud} bit/s, "
        f"8N1, slave={args.address}, FC03"
    )
    print("POTWIERDZONE = zgodne z panelem; HIPOTEZA = opis roboczy.")
    print("Wartości raw i ramki są rzeczywistymi odpowiedziami urządzenia.")

    any_response = False
    for address in range(args.start, args.end + 1):
        definition = REGISTERS.get(
            address,
            RegisterDefinition(address, f"nieznany parametr {address}", "raw"),
        )
        try:
            raw, tx, rx = read_register(port, args.address, address, args.timeout)
            signed = signed16(raw)
            rendered = display_value(definition, raw)
            print(
                f"ADR {address}: [{definition.confidence:<12}] "
                f"{definition.description:<42} raw={raw:<5} "
                f"signed={signed:<6} wartość={rendered}"
            )
            if args.show_frames:
                print(f"      TX {tx.hex(' ').upper()}")
                print(f"      RX {rx.hex(' ').upper()}")
            writer.writerow(
                (
                    datetime.now().isoformat(timespec="milliseconds"),
                    address,
                    definition.confidence,
                    definition.description,
                    raw,
                    signed,
                    f"{signed / 10.0:.1f}",
                    rendered,
                    tx.hex(" ").upper(),
                    rx.hex(" ").upper(),
                    "OK",
                )
            )
            any_response = True
        except ModbusError as exc:
            writer.writerow(
                (
                    datetime.now().isoformat(timespec="milliseconds"),
                    address,
                    definition.confidence,
                    definition.description,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    str(exc),
                )
            )
        time.sleep(args.delay)
    return any_response


def main() -> int:
    args = parse_args()
    validate_args(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print("TRYB TYLKO DO ODCZYTU — skrypt wysyła wyłącznie FC03.")
    print("Nie używać opisów HIPOTEZA jako podstawy do zapisów Modbus.")

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
            writer.writerow(
                (
                    "timestamp",
                    "address",
                    "confidence",
                    "description",
                    "raw_u16",
                    "signed_i16",
                    "div10",
                    "display_value",
                    "tx_hex",
                    "rx_hex",
                    "status",
                )
            )

            while True:
                success = run_cycle(port, args, writer)
                handle.flush()
                if not args.continuous:
                    print(f"\nZapisano log: {output}")
                    return 0 if success else 1
                print(f"\nNastępny odczyt za {args.interval:.1f} s. Ctrl+C kończy.")
                time.sleep(args.interval)
    except serial.SerialException as exc:
        print(f"BŁĄD portu {args.port}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
