#!/usr/bin/env python3
"""Guarded Modbus RTU control test for COMPIT NANO COLOR 2 v6.30.

Known transport:
- COM10 (default)
- 9600 bit/s, 8N1
- slave 44
- FC03 read, FC06 write single register

Allowed control addresses:
- 1080: ventilation mode / speed (0..3 used in Stage 1)
- 1081: airing (0/1)

Observed runtime behavior:
- NANO may acknowledge a write immediately,
- AERO 4A2 may need up to about 30 seconds to execute it physically,
- protocol acknowledgement is not treated as physical confirmation,
- the tool observes fan-power telemetry for up to 45 seconds by default.

Safety:
- writes require --execute and --confirm NANO630,
- the previous value is read first,
- FC06 echo and FC03 readback are verified,
- the physical response is observed separately,
- the previous value is restored unless --keep is used.
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from dataclasses import dataclass

try:
    import serial
except ImportError as exc:
    raise SystemExit("Brak pyserial. Zainstaluj: py -m pip install pyserial") from exc


FC03 = 0x03
FC06 = 0x06

DEFAULT_PORT = "COM10"
DEFAULT_SLAVE = 44
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 0.6
DEFAULT_SETTLE_TIMEOUT = 45.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_HOLD_SECONDS = 10.0
CONFIRM_TEXT = "NANO630"

ADDR_SPEED = 1080
ADDR_AIRING = 1081
ADDR_FAN_1_POWER = 2033
ADDR_FAN_2_POWER = 2034

TELEMETRY = (
    (2016, "wilgotność", "div10_percent"),
    (2021, "temperatura nawiewu", "temperature"),
    (2022, "temperatura wywiewu", "temperature"),
    (2023, "temperatura czerpni", "temperature"),
    (ADDR_FAN_1_POWER, "moc wentylatora 1", "percent"),
    (ADDR_FAN_2_POWER, "moc wentylatora 2", "percent"),
)


class ModbusError(RuntimeError):
    """Raised for missing, malformed or rejected Modbus exchanges."""


@dataclass(frozen=True)
class Exchange:
    tx: bytes
    rx: bytes


@dataclass(frozen=True)
class FanPower:
    fan_1: int
    fan_2: int

    def render(self) -> str:
        return f"wentylator1={self.fan_1}% wentylator2={self.fan_2}%"


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
) -> tuple[int, Exchange]:
    request = append_crc(struct.pack(">BBHH", slave, FC03, address, 1))
    port.reset_input_buffer()
    port.write(request)
    port.flush()

    header = read_exact(port, 3, timeout)
    if len(header) != 3:
        raise ModbusError(f"ADR {address}: brak odpowiedzi")

    rx_slave, function, third = header
    if rx_slave != slave:
        raise ModbusError(
            f"ADR {address}: odpowiedź slave={rx_slave}, oczekiwano {slave}"
        )

    if function == (FC03 | 0x80):
        tail = read_exact(port, 2, timeout)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError(f"ADR {address}: niepełna odpowiedź wyjątkowa")
        verify_crc(frame)
        raise ModbusError(f"ADR {address}: wyjątek Modbus 0x{third:02X}")

    if function != FC03 or third != 2:
        raise ModbusError(
            f"ADR {address}: nieoczekiwana odpowiedź "
            f"FC=0x{function:02X}, bytes={third}"
        )

    tail = read_exact(port, 4, timeout)
    frame = header + tail
    if len(frame) != 7:
        raise ModbusError(f"ADR {address}: niepełna odpowiedź")

    verify_crc(frame)
    value = struct.unpack(">H", frame[3:5])[0]
    return value, Exchange(request, frame)


def write_register(
    port: serial.Serial,
    slave: int,
    address: int,
    value: int,
    timeout: float,
) -> Exchange:
    request = append_crc(struct.pack(">BBHH", slave, FC06, address, value))
    port.reset_input_buffer()
    port.write(request)
    port.flush()

    response = read_exact(port, 8, timeout)
    if len(response) != 8:
        raise ModbusError(
            f"ADR {address}: brak pełnej odpowiedzi FC06 "
            f"({len(response)}/8 bajtów)"
        )

    verify_crc(response)
    if response != request:
        raise ModbusError(
            f"ADR {address}: odpowiedź FC06 nie jest echem żądania\n"
            f"TX {request.hex(' ').upper()}\n"
            f"RX {response.hex(' ').upper()}"
        )
    return Exchange(request, response)


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def render(kind: str, raw: int) -> str:
    signed = signed16(raw)
    if kind == "temperature":
        return f"{signed / 10.0:.1f} °C"
    if kind == "div10_percent":
        return f"{raw / 10.0:.1f} %"
    if kind == "percent":
        return f"{raw} %"
    return str(raw)


def show_exchange(exchange: Exchange) -> None:
    print(f"      TX {exchange.tx.hex(' ').upper()}")
    print(f"      RX {exchange.rx.hex(' ').upper()}")


def read_fan_power(port: serial.Serial, args: argparse.Namespace) -> FanPower:
    fan_1, _ = read_register(
        port, args.address, ADDR_FAN_1_POWER, args.timeout
    )
    fan_2, _ = read_register(
        port, args.address, ADDR_FAN_2_POWER, args.timeout
    )
    return FanPower(fan_1=fan_1, fan_2=fan_2)


def show_status(port: serial.Serial, args: argparse.Namespace) -> None:
    print("\nStan sterowania:")
    controls = (
        (ADDR_SPEED, "tryb/bieg wentylacji"),
        (ADDR_AIRING, "wietrzenie"),
    )
    for address, label in controls:
        value, exchange = read_register(
            port, args.address, address, args.timeout
        )
        print(f"ADR {address}: {label:<28} raw={value}")
        if args.show_frames:
            show_exchange(exchange)

    print("\nPotwierdzona telemetria:")
    for address, label, kind in TELEMETRY:
        value, exchange = read_register(
            port, args.address, address, args.timeout
        )
        print(
            f"ADR {address}: {label:<28} "
            f"raw={value:<5} wartość={render(kind, value)}"
        )
        if args.show_frames:
            show_exchange(exchange)


def require_write_confirmation(args: argparse.Namespace) -> None:
    if not args.execute:
        raise SystemExit(
            "TRYB PODGLĄDU: nie wykonano zapisu. "
            "Dodaj --execute --confirm NANO630, aby uruchomić test."
        )
    if args.confirm != CONFIRM_TEXT:
        raise SystemExit(
            f"Brak poprawnego potwierdzenia. Wymagane: --confirm {CONFIRM_TEXT}"
        )


def verify_control_readback(
    port: serial.Serial,
    args: argparse.Namespace,
    address: int,
    expected: int,
    phase: str,
) -> None:
    time.sleep(args.verify_delay)
    readback, exchange = read_register(
        port, args.address, address, args.timeout
    )
    print(f"{phase} — odczyt ADR {address}: {readback}")
    if args.show_frames:
        show_exchange(exchange)
    if readback != expected:
        raise ModbusError(
            f"ADR {address}: {phase.lower()} niepotwierdzone, "
            f"odczytano {readback}, oczekiwano {expected}"
        )
    print(
        f"{phase} potwierdzone na poziomie Modbus. "
        "To nie oznacza jeszcze fizycznej reakcji AERO."
    )


def wait_for_fan_change(
    port: serial.Serial,
    args: argparse.Namespace,
    baseline: FanPower,
    phase: str,
) -> tuple[FanPower, bool]:
    print(
        f"\n{phase}: obserwuję fizyczną odpowiedź AERO przez maksymalnie "
        f"{args.settle_timeout:.1f} s."
    )
    deadline = time.monotonic() + args.settle_timeout
    started = time.monotonic()
    last = baseline

    while True:
        now = time.monotonic()
        if now >= deadline:
            print(
                f"OSTRZEŻENIE: brak zmiany mocy wentylatorów w czasie "
                f"{args.settle_timeout:.1f} s. Ostatni stan: {last.render()}."
            )
            return last, False

        time.sleep(min(args.poll_interval, max(0.0, deadline - now)))
        last = read_fan_power(port, args)
        elapsed = time.monotonic() - started
        print(f"  t={elapsed:5.1f} s  {last.render()}")

        if last != baseline:
            print(
                f"Fizyczna reakcja AERO zaobserwowana po {elapsed:.1f} s."
            )
            return last, True


def wait_for_fan_return(
    port: serial.Serial,
    args: argparse.Namespace,
    baseline: FanPower,
) -> bool:
    print(
        f"\nPo przywróceniu obserwuję powrót mocy przez maksymalnie "
        f"{args.settle_timeout:.1f} s."
    )
    deadline = time.monotonic() + args.settle_timeout
    started = time.monotonic()
    last = read_fan_power(port, args)

    while True:
        elapsed = time.monotonic() - started
        print(f"  t={elapsed:5.1f} s  {last.render()}")
        if last == baseline:
            print(
                f"Powrót fizyczny potwierdzony po {elapsed:.1f} s."
            )
            return True

        now = time.monotonic()
        if now >= deadline:
            print(
                "OSTRZEŻENIE: rejestr sterujący został przywrócony, ale "
                f"moce nie wróciły do stanu bazowego w {args.settle_timeout:.1f} s. "
                f"Stan bazowy: {baseline.render()}, ostatni: {last.render()}."
            )
            return False

        time.sleep(min(args.poll_interval, max(0.0, deadline - now)))
        last = read_fan_power(port, args)


def execute_guarded_change(
    port: serial.Serial,
    args: argparse.Namespace,
    address: int,
    target: int,
    label: str,
    allowed_previous: set[int],
) -> None:
    previous, before_exchange = read_register(
        port, args.address, address, args.timeout
    )
    baseline_power = read_fan_power(port, args)

    print(f"\n{label}: ADR {address}, obecnie={previous}, cel={target}")
    print(f"Stan fizyczny przed zmianą: {baseline_power.render()}")
    if args.show_frames:
        show_exchange(before_exchange)

    if previous not in allowed_previous:
        raise SystemExit(
            f"ODMOWA: bieżąca wartość {previous} nie należy do oczekiwanego "
            f"zakresu {sorted(allowed_previous)}."
        )

    if previous == target:
        print("Wartość docelowa jest już aktywna. Zapis nie jest potrzebny.")
        return

    if not args.execute:
        print(
            "TRYB PODGLĄDU: zapis nie został wykonany. "
            f"Komenda testowa wymaga --execute --confirm {CONFIRM_TEXT}."
        )
        return

    require_write_confirmation(args)

    print("Wykonuję pojedynczy zapis FC06...")
    write_exchange = write_register(
        port, args.address, address, target, args.timeout
    )
    if args.show_frames:
        show_exchange(write_exchange)

    verify_control_readback(
        port, args, address, target, "Zapis wartości docelowej"
    )
    physical_after, changed = wait_for_fan_change(
        port, args, baseline_power, "Weryfikacja wykonania"
    )

    print("\nStan po okresie oczekiwania:")
    show_status(port, args)

    if args.keep:
        if not changed:
            print(
                "\n--keep: wartość sterująca pozostaje aktywna, mimo że "
                "zmiana mocy nie została jeszcze potwierdzona."
            )
        else:
            print(
                f"\n--keep: nowa wartość pozostaje aktywna; "
                f"ostatnia moc: {physical_after.render()}."
            )
        return

    print(
        f"\nPo potwierdzeniu/wyczerpaniu czasu bezwładności utrzymuję test "
        f"jeszcze przez {args.hold_seconds:.1f} s, a następnie przywrócę "
        f"wartość {previous}."
    )
    time.sleep(args.hold_seconds)

    restore_exchange = write_register(
        port, args.address, address, previous, args.timeout
    )
    if args.show_frames:
        show_exchange(restore_exchange)

    verify_control_readback(
        port, args, address, previous, "Przywrócenie wartości poprzedniej"
    )
    wait_for_fan_return(port, args, baseline_power)


def add_write_safety_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=DEFAULT_HOLD_SECONDS,
        help=(
            "Czas utrzymania po potwierdzeniu lub zakończeniu oczekiwania "
            f"na AERO (domyślnie {DEFAULT_HOLD_SECONDS:.0f} s)"
        ),
    )
    parser.add_argument(
        "--verify-delay",
        type=float,
        default=0.8,
        help="Opóźnienie przed kontrolnym odczytem rejestru Modbus",
    )
    parser.add_argument(
        "--settle-timeout",
        type=float,
        default=DEFAULT_SETTLE_TIMEOUT,
        help=(
            "Maksymalny czas oczekiwania na fizyczną reakcję AERO "
            f"(domyślnie {DEFAULT_SETTLE_TIMEOUT:.0f} s)"
        ),
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help=(
            "Odstęp odczytów mocy podczas oczekiwania "
            f"(domyślnie {DEFAULT_POLL_INTERVAL:.0f} s)"
        ),
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Nie przywracaj poprzedniej wartości po teście",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--address", type=int, default=DEFAULT_SLAVE)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--show-frames", action="store_true")

    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status", help="Odczytaj sterowanie i telemetrię")

    speed = commands.add_parser(
        "speed",
        help="Test zmiany biegu 0..3 przez ADR 1080",
    )
    speed.add_argument("value", type=int, choices=range(0, 4))
    add_write_safety_options(speed)

    airing = commands.add_parser(
        "airing",
        help="Test wietrzenia przez ADR 1081",
    )
    airing.add_argument("state", choices=("on", "off"))
    add_write_safety_options(airing)

    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.address <= 247:
        raise SystemExit("Adres slave musi należeć do zakresu 1..247")
    if args.baud <= 0 or args.timeout <= 0:
        raise SystemExit("Baud i timeout muszą być dodatnie")
    if hasattr(args, "hold_seconds") and args.hold_seconds < 0:
        raise SystemExit("--hold-seconds nie może być ujemne")
    if hasattr(args, "verify_delay") and args.verify_delay <= 0:
        raise SystemExit("--verify-delay musi być dodatnie")
    if hasattr(args, "settle_timeout") and args.settle_timeout <= 0:
        raise SystemExit("--settle-timeout musi być dodatnie")
    if hasattr(args, "poll_interval") and args.poll_interval <= 0:
        raise SystemExit("--poll-interval musi być dodatnie")
    if hasattr(args, "poll_interval") and hasattr(args, "settle_timeout"):
        if args.poll_interval > args.settle_timeout:
            raise SystemExit("--poll-interval nie może przekraczać --settle-timeout")
    if hasattr(args, "keep") and args.keep and not args.execute:
        raise SystemExit("--keep wymaga --execute")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    print("COMPIT NANO COLOR 2 v6.30 — kontrolowany test Modbus")
    print(
        f"{args.port}, {args.baud} bit/s, 8N1, "
        f"slave={args.address}"
    )
    print("Do zapisu dopuszczone są wyłącznie ADR 1080 i 1081.")
    print(
        "Ważne: echo FC06 i readback potwierdzają przyjęcie polecenia przez "
        "NANO, a nie fizyczne wykonanie przez AERO."
    )

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
            if args.command == "status":
                show_status(port, args)
                return 0
            if args.command == "speed":
                execute_guarded_change(
                    port,
                    args,
                    ADDR_SPEED,
                    args.value,
                    "Tryb/bieg wentylacji",
                    set(range(0, 6)),
                )
                return 0
            if args.command == "airing":
                execute_guarded_change(
                    port,
                    args,
                    ADDR_AIRING,
                    1 if args.state == "on" else 0,
                    "Wietrzenie",
                    {0, 1},
                )
                return 0
            parser.error("nieznana komenda")
    except (serial.SerialException, ModbusError) as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
