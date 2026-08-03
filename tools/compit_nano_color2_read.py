#!/usr/bin/env python3
"""Read-only Modbus RTU test for COMPIT NANO COLOR 2 / AERO 4A2.

Known project parameters:
- slave address: 44
- 9600 bit/s
- 8N1
- function: 0x03 Read Holding Registers

The tool contains no Modbus write function.
Dependency:
    py -m pip install pyserial
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
    raise SystemExit(
        "Brak biblioteki pyserial. Zainstaluj: py -m pip install pyserial"
    ) from exc


FUNCTION_READ_HOLDING_REGISTERS = 0x03
DEFAULT_PORT = "COM10"
DEFAULT_SLAVE_ADDRESS = 44
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT_SECONDS = 0.6

FIRST_VALIDATION_REGISTERS = (2016, 2021, 2036, 2039, 2040)
FULL_STATUS_REGISTERS = (
    2016,
    2021,
    2022,
    2023,
    2024,
    2026,
    2028,
    2031,
    2034,
    2035,
    2036,
    2037,
    2039,
    2040,
)


@dataclass(frozen=True)
class RegisterDefinition:
    name: str
    unit: str = ""
    scale: float = 1.0
    signed: bool = False
    values: dict[int, str] | None = None


REGISTER_DEFINITIONS: dict[int, RegisterDefinition] = {
    2016: RegisterDefinition("temperatura pomieszczenia", "°C", 10.0, True),
    2021: RegisterDefinition("temperatura nawiewu", "°C", 10.0, True),
    2022: RegisterDefinition("temperatura czerpni / zewnętrzna", "°C", 10.0, True),
    2023: RegisterDefinition("temperatura wywiewu", "°C", 10.0, True),
    2024: RegisterDefinition("temperatura wyrzutni", "°C", 10.0, True),
    2026: RegisterDefinition("aktywne rozmrażanie", values={0: "nie", 1: "tak"}),
    2028: RegisterDefinition("aktywne wietrzenie", values={0: "nie", 1: "tak"}),
    2031: RegisterDefinition("zabrudzony filtr", values={0: "nie", 1: "tak"}),
    2034: RegisterDefinition("aktualna wydajność nawiewu", "%"),
    2035: RegisterDefinition("aktualna wydajność wywiewu", "%"),
    2036: RegisterDefinition(
        "aktualny bieg wentylacji",
        values={
            0: "bieg 0",
            1: "bieg 1",
            2: "bieg 2",
            3: "bieg 3",
            4: "program świąteczny",
            5: "harmonogram",
        },
    ),
    2037: RegisterDefinition(
        "stan bypassu",
        values={0: "wyłączony", 1: "auto", 2: "włączony"},
    ),
    2039: RegisterDefinition("rozpoznany moduł wentylacji"),
    2040: RegisterDefinition("alarm AERO"),
}


class ModbusError(RuntimeError):
    """Raised for malformed, missing or exceptional Modbus responses."""


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def append_crc(frame: bytes) -> bytes:
    crc = crc16_modbus(frame)
    return frame + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusError(f"Za krótka odpowiedź: {frame.hex(' ').upper()}")
    received = frame[-2] | (frame[-1] << 8)
    expected = crc16_modbus(frame[:-2])
    if received != expected:
        raise ModbusError(
            f"Błędne CRC: odebrane=0x{received:04X}, oczekiwane=0x{expected:04X}"
        )


def read_exact(port: serial.Serial, size: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    result = bytearray()
    while len(result) < size and time.monotonic() < deadline:
        chunk = port.read(size - len(result))
        if chunk:
            result.extend(chunk)
    return bytes(result)


def build_read_request(slave: int, pdu_address: int) -> bytes:
    if not 0 <= pdu_address <= 0xFFFF:
        raise ValueError(f"Adres PDU poza zakresem uint16: {pdu_address}")
    pdu = struct.pack(
        ">BBHH",
        slave,
        FUNCTION_READ_HOLDING_REGISTERS,
        pdu_address,
        1,
    )
    return append_crc(pdu)


def read_register(
    port: serial.Serial,
    slave: int,
    documented_register: int,
    pdu_offset: int,
    timeout: float,
) -> tuple[int, bytes, bytes]:
    pdu_address = documented_register + pdu_offset
    request = build_read_request(slave, pdu_address)

    port.reset_input_buffer()
    port.write(request)
    port.flush()

    header = read_exact(port, 3, timeout)
    if len(header) != 3:
        raise ModbusError("Brak odpowiedzi lub niepełny nagłówek")

    response_slave, function, third = header
    if response_slave != slave:
        raise ModbusError(
            f"Odpowiedź z adresu {response_slave}, oczekiwano {slave}"
        )

    if function == (FUNCTION_READ_HOLDING_REGISTERS | 0x80):
        tail = read_exact(port, 2, timeout)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError("Niepełna odpowiedź wyjątkowa")
        verify_crc(frame)
        exception_names = {
            1: "Illegal Function",
            2: "Illegal Data Address",
            3: "Illegal Data Value",
            4: "Slave Device Failure",
            6: "Slave Device Busy",
        }
        raise ModbusError(
            f"Wyjątek Modbus 0x{third:02X} "
            f"({exception_names.get(third, 'nieznany')})"
        )

    if function != FUNCTION_READ_HOLDING_REGISTERS:
        raise ModbusError(f"Nieoczekiwany kod funkcji 0x{function:02X}")
    if third != 2:
        raise ModbusError(f"Nieoczekiwana liczba bajtów danych: {third}")

    tail = read_exact(port, 4, timeout)
    frame = header + tail
    if len(frame) != 7:
        raise ModbusError("Niepełna odpowiedź rejestru")
    verify_crc(frame)

    value = struct.unpack(">H", frame[3:5])[0]
    return value, request, frame


def signed_u16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def decode_value(register: int, raw: int) -> str:
    definition = REGISTER_DEFINITIONS[register]
    numeric = signed_u16(raw) if definition.signed else raw

    if definition.values and numeric in definition.values:
        return f"{definition.values[numeric]} ({numeric})"

    scaled = numeric / definition.scale
    if definition.scale == 1.0:
        rendered = str(int(scaled))
    else:
        rendered = f"{scaled:.1f}"

    return f"{rendered} {definition.unit}".strip()


def open_log(path: str | None):
    if not path:
        return None, None
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = output.open("w", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    writer.writerow(
        (
            "timestamp",
            "register",
            "pdu_address",
            "name",
            "raw",
            "decoded",
            "tx_hex",
            "rx_hex",
            "result",
        )
    )
    return handle, writer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--address", type=int, default=DEFAULT_SLAVE_ADDRESS)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--pdu-offset",
        type=int,
        default=0,
        help=(
            "Różnica między numerem z dokumentacji a adresem PDU. "
            "Domyślnie 0; nie zmieniać bez potwierdzenia dokumentacji."
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Odczytaj pełny zestaw znanych rejestrów stanu.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Powtarzaj odczyt do Ctrl+C.",
    )
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--log", default="compit_nano_color2_read.csv")
    parser.add_argument(
        "--show-frames",
        action="store_true",
        help="Pokaż surowe ramki TX i RX.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.address <= 247:
        raise SystemExit("Adres Modbus musi należeć do zakresu 1-247")
    if args.baud <= 0 or args.timeout <= 0 or args.interval <= 0:
        raise SystemExit("Baud, timeout i interval muszą być dodatnie")


def run_cycle(
    port: serial.Serial,
    args: argparse.Namespace,
    registers: tuple[int, ...],
    writer,
) -> bool:
    success = True
    print(
        f"\nCOMPIT NANO COLOR 2: {args.port}, "
        f"{args.baud} bit/s, 8N1, slave={args.address}, FC03"
    )

    for register in registers:
        definition = REGISTER_DEFINITIONS[register]
        pdu_address = register + args.pdu_offset
        try:
            raw, tx, rx = read_register(
                port,
                args.address,
                register,
                args.pdu_offset,
                args.timeout,
            )
            decoded = decode_value(register, raw)
            print(
                f"{register}: {definition.name:<38} "
                f"raw={raw:<5}  {decoded}"
            )
            if args.show_frames:
                print(f"      TX {tx.hex(' ').upper()}")
                print(f"      RX {rx.hex(' ').upper()}")
            if writer:
                writer.writerow(
                    (
                        datetime.now().isoformat(timespec="milliseconds"),
                        register,
                        pdu_address,
                        definition.name,
                        raw,
                        decoded,
                        tx.hex(" ").upper(),
                        rx.hex(" ").upper(),
                        "OK",
                    )
                )
        except ModbusError as exc:
            success = False
            print(f"{register}: {definition.name:<38} BŁĄD: {exc}")
            if writer:
                writer.writerow(
                    (
                        datetime.now().isoformat(timespec="milliseconds"),
                        register,
                        pdu_address,
                        definition.name,
                        "",
                        "",
                        "",
                        "",
                        str(exc),
                    )
                )
        time.sleep(0.05)

    return success


def main() -> int:
    args = parse_args()
    validate_args(args)
    registers = FULL_STATUS_REGISTERS if args.full else FIRST_VALIDATION_REGISTERS
    handle, writer = open_log(args.log)

    print("TRYB TYLKO DO ODCZYTU.")
    print("Skrypt wysyła wyłącznie Modbus FC03 i nie zawiera funkcji zapisu.")
    print("Uruchamiać dopiero po potwierdzeniu zacisków Modbus/BMS panelu NANO COLOR 2.")
    print("Nie podłączać do nieustalonej pary C14 AERO 4A2.")

    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.02,
            write_timeout=args.timeout,
        ) as port:
            while True:
                success = run_cycle(port, args, registers, writer)
                if handle:
                    handle.flush()
                if not args.continuous:
                    return 0 if success else 1
                print(f"\nNastępny odczyt za {args.interval:.1f} s. Ctrl+C kończy.")
                time.sleep(args.interval)
    except serial.SerialException as exc:
        print(f"Nie można użyć portu {args.port}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    finally:
        if handle:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
