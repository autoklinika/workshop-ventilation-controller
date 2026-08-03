#!/usr/bin/env python3
"""Read the KAmod + SEN55 Stage 2 Modbus RTU input-register map."""

from __future__ import annotations

import argparse
import struct
import sys
import time
from dataclasses import dataclass

try:
    import serial
except ImportError as exc:  # pragma: no cover - user environment guard
    raise SystemExit(
        "Brak biblioteki pyserial. Zainstaluj: py -m pip install pyserial"
    ) from exc


REGISTER_COUNT = 19
FUNCTION_READ_INPUT_REGISTERS = 0x04

AVAILABILITY_NAMES = (
    "PM1.0",
    "PM2.5",
    "PM4.0",
    "PM10",
    "RH",
    "T",
    "VOC",
    "NOx",
)

STATUS_NAMES = (
    "measurement_valid",
    "sensor_present",
    "measurement_stale",
    "i2c_error",
    "data_error",
    "initializing",
    "sensor_offline",
    "platform_fault",
)


class ModbusError(RuntimeError):
    pass


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(frame: bytes) -> bytes:
    crc = crc16_modbus(frame)
    return frame + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusError(f"Za krótka ramka: {frame.hex(' ')}")
    expected = crc16_modbus(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
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


def read_input_registers(
    port: serial.Serial,
    slave_address: int,
    start_address: int = 0,
    quantity: int = REGISTER_COUNT,
) -> list[int]:
    request_pdu = struct.pack(">BBHH", slave_address, FUNCTION_READ_INPUT_REGISTERS,
                              start_address, quantity)
    request = append_crc(request_pdu)

    port.reset_input_buffer()
    port.write(request)
    port.flush()

    header = read_exact(port, 3, port.timeout or 1.0)
    if len(header) != 3:
        raise ModbusError("Brak odpowiedzi lub niepełny nagłówek Modbus")

    response_address, function, third = header
    if response_address != slave_address:
        raise ModbusError(
            f"Odpowiedź z nieoczekiwanego adresu {response_address}, oczekiwano {slave_address}"
        )

    if function == (FUNCTION_READ_INPUT_REGISTERS | 0x80):
        tail = read_exact(port, 2, port.timeout or 1.0)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError("Niepełna odpowiedź wyjątkowa Modbus")
        verify_crc(frame)
        raise ModbusError(f"Wyjątek Modbus 0x{third:02X}")

    if function != FUNCTION_READ_INPUT_REGISTERS:
        raise ModbusError(f"Nieoczekiwany kod funkcji 0x{function:02X}")

    expected_byte_count = quantity * 2
    if third != expected_byte_count:
        raise ModbusError(
            f"Nieoczekiwana długość danych {third}, oczekiwano {expected_byte_count}"
        )

    tail = read_exact(port, third + 2, port.timeout or 1.0)
    frame = header + tail
    if len(frame) != 3 + third + 2:
        raise ModbusError("Niepełna odpowiedź Modbus")
    verify_crc(frame)

    payload = frame[3:-2]
    return list(struct.unpack(f">{quantity}H", payload))


def signed_16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def combine_u32(high: int, low: int) -> int:
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def active_bits(value: int, names: tuple[str, ...]) -> list[str]:
    return [name for bit, name in enumerate(names) if value & (1 << bit)]


def field_value(registers: list[int], index: int, mask: int, bit: int, scale: float) -> str:
    if not (mask & (1 << bit)):
        return "niedostępne"
    return f"{registers[index] / scale:.2f}"


@dataclass(frozen=True)
class Decoded:
    pm1_0: str
    pm2_5: str
    pm4_0: str
    pm10_0: str
    humidity: str
    temperature: str
    voc: str
    nox: str
    availability: list[str]
    status: list[str]
    age_seconds: int | None
    sensor_errors: int
    modbus_errors: int
    uptime_seconds: int
    firmware_version: str
    map_version: int
    sequence: int


def decode(registers: list[int]) -> Decoded:
    if len(registers) != REGISTER_COUNT:
        raise ValueError(f"Oczekiwano {REGISTER_COUNT} rejestrów, odebrano {len(registers)}")

    availability_mask = registers[8] & 0xFF
    status_mask = registers[9]
    age = None if registers[10] == 0xFFFF else registers[10]

    temperature = "niedostępne"
    if availability_mask & (1 << 5):
        temperature = f"{signed_16(registers[5]) / 100.0:.2f}"

    firmware = registers[15]
    return Decoded(
        pm1_0=field_value(registers, 0, availability_mask, 0, 10.0),
        pm2_5=field_value(registers, 1, availability_mask, 1, 10.0),
        pm4_0=field_value(registers, 2, availability_mask, 2, 10.0),
        pm10_0=field_value(registers, 3, availability_mask, 3, 10.0),
        humidity=field_value(registers, 4, availability_mask, 4, 100.0),
        temperature=temperature,
        voc=field_value(registers, 6, availability_mask, 6, 10.0),
        nox=field_value(registers, 7, availability_mask, 7, 10.0),
        availability=active_bits(availability_mask, AVAILABILITY_NAMES),
        status=active_bits(status_mask, STATUS_NAMES),
        age_seconds=age,
        sensor_errors=registers[11],
        modbus_errors=registers[12],
        uptime_seconds=combine_u32(registers[13], registers[14]),
        firmware_version=f"{(firmware >> 8) & 0xFF}.{firmware & 0xFF}",
        map_version=registers[16],
        sequence=combine_u32(registers[17], registers[18]),
    )


def print_decoded(value: Decoded) -> None:
    age = "brak" if value.age_seconds is None else f"{value.age_seconds} s"
    print(
        f"PM1.0={value.pm1_0}  PM2.5={value.pm2_5}  PM4.0={value.pm4_0}  "
        f"PM10={value.pm10_0} µg/m³"
    )
    print(
        f"RH={value.humidity}%  T={value.temperature}°C  "
        f"VOC={value.voc}  NOx={value.nox}"
    )
    print(
        f"status={','.join(value.status) or '0'}  "
        f"availability={','.join(value.availability) or '0'}  age={age}"
    )
    print(
        f"sensor_errors={value.sensor_errors}  modbus_errors={value.modbus_errors}  "
        f"uptime={value.uptime_seconds}s  sequence={value.sequence}  "
        f"fw={value.firmware_version}  map={value.map_version}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Port konwertera USB–RS485, np. COM10")
    parser.add_argument("--baud", type=int, default=19200)
    parser.add_argument("--address", type=int, default=1)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.address <= 247:
        raise SystemExit("Adres Modbus musi należeć do zakresu 1–247")
    if args.interval <= 0 or args.timeout <= 0:
        raise SystemExit("Interval i timeout muszą być dodatnie")

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
            while True:
                try:
                    registers = read_input_registers(port, args.address)
                    print_decoded(decode(registers))
                except ModbusError as exc:
                    print(f"BŁĄD: {exc}", file=sys.stderr)
                if args.once:
                    break
                print("-" * 88)
                time.sleep(args.interval)
    except serial.SerialException as exc:
        print(f"Nie można użyć portu {args.port}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
