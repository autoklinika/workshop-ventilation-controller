from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ventilation_core.rs485.modbus import (
    build_read_holding_registers_request,
    build_read_input_registers_request,
    parse_read_holding_registers_response,
    parse_read_input_registers_response,
)
from ventilation_core.rs485.ports import discover_serial_ports
from ventilation_core.rs485.serial_transport import SerialSettings
from ventilation_core.rs485.worker import ProcessRS485Master


DEFAULT_LOOPBACK_PAYLOAD = bytes.fromhex("57 56 43 32 2D 52 53 34 38 35")


def _integer(value: str) -> int:
    return int(value, 0)


def _hex_bytes(value: str) -> bytes:
    cleaned = "".join(character for character in value if character not in " :-_")
    if not cleaned or len(cleaned) % 2:
        raise argparse.ArgumentTypeError(
            "payload must contain a non-empty, even number of hexadecimal digits"
        )
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("payload contains non-hexadecimal data") from exc


def _add_line_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--parity", choices=("N", "E", "O"), default="N")
    parser.add_argument("--stopbits", type=int, choices=(1, 2), default=1)
    parser.add_argument("--bytesize", type=int, choices=(7, 8), default=8)
    parser.add_argument("--timeout", type=float, default=0.5)


def _add_serial_arguments(
    parser: argparse.ArgumentParser,
    *,
    multiple_ports: bool = False,
) -> None:
    if multiple_ports:
        parser.add_argument(
            "--port",
            action="append",
            required=True,
            help="serial device path; repeat for each independent UART",
        )
    else:
        parser.add_argument("--port", required=True)
    _add_line_arguments(parser)


def _add_read_arguments(parser: argparse.ArgumentParser) -> None:
    _add_serial_arguments(parser)
    parser.add_argument("--slave", type=_integer, required=True)
    parser.add_argument("--address", type=_integer, required=True)
    parser.add_argument("--count", type=int, default=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RS-485 / Modbus RTU bring-up tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "ports", help="list detected onboard UART and USB serial interfaces"
    )

    check_ports = subparsers.add_parser(
        "check-ports",
        help="open one or more UARTs in separate workers without transmitting data",
    )
    _add_serial_arguments(check_ports, multiple_ports=True)

    loopback = subparsers.add_parser(
        "loopback",
        help="send a fixed pattern between two RS-485 adapters in both directions",
    )
    loopback.add_argument("--port-a", required=True)
    loopback.add_argument("--port-b", required=True)
    _add_line_arguments(loopback)
    loopback.add_argument(
        "--payload",
        type=_hex_bytes,
        default=DEFAULT_LOOPBACK_PAYLOAD,
        help="hexadecimal test payload; default is ASCII WVC2-RS485",
    )
    loopback.add_argument(
        "--settle",
        type=float,
        default=0.05,
        help="seconds between arming the receiver and starting transmission",
    )

    holding = subparsers.add_parser(
        "read-holding", help="read Modbus holding registers (function 0x03)"
    )
    _add_read_arguments(holding)
    input_registers = subparsers.add_parser(
        "read-input", help="read Modbus input registers (function 0x04)"
    )
    _add_read_arguments(input_registers)
    return parser


def _ports_response() -> dict[str, Any]:
    ports = [port.to_dict() for port in discover_serial_ports()]
    return {"ok": True, "ports": ports, "count": len(ports)}


def _settings(args: argparse.Namespace, port: str) -> SerialSettings:
    return SerialSettings(
        port=port,
        baudrate=args.baudrate,
        parity=args.parity,
        stopbits=args.stopbits,
        bytesize=args.bytesize,
        timeout_seconds=args.timeout,
    )


def _check_ports(args: argparse.Namespace) -> dict[str, Any]:
    ports = list(dict.fromkeys(args.port))
    if len(ports) != len(args.port):
        raise ValueError("Each UART port may be specified only once")

    masters: list[ProcessRS485Master] = []
    try:
        for port in ports:
            master = ProcessRS485Master(
                _settings(args, port),
                timeout_seconds=max(3.0, args.timeout + 1.0),
            )
            masters.append(master)
            master.ping()
        return {
            "ok": True,
            "ports": [{"port": master.port, "ready": master.ready} for master in masters],
            "count": len(masters),
            "transmitted": False,
        }
    finally:
        for master in reversed(masters):
            master.close()


def _one_way_loopback(
    sender: ProcessRS485Master,
    receiver: ProcessRS485Master,
    payload: bytes,
    *,
    settle_seconds: float,
    result_timeout: float,
) -> bytes:
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_read = executor.submit(receiver.read_exact, len(payload))
        time.sleep(settle_seconds)
        written = sender.write_raw(payload)
        if written != len(payload):
            raise RuntimeError(
                f"Loopback sender wrote {written} of {len(payload)} bytes"
            )
        return pending_read.result(timeout=result_timeout)


def _loopback(args: argparse.Namespace) -> dict[str, Any]:
    if args.port_a == args.port_b:
        raise ValueError("Loopback requires two different UART ports")
    if args.settle < 0:
        raise ValueError("Loopback settle time cannot be negative")
    payload = bytes(args.payload)
    if not payload:
        raise ValueError("Loopback payload cannot be empty")

    worker_timeout = max(3.0, args.timeout + 1.0)
    master_a = ProcessRS485Master(
        _settings(args, args.port_a), timeout_seconds=worker_timeout
    )
    master_b: ProcessRS485Master | None = None
    try:
        master_b = ProcessRS485Master(
            _settings(args, args.port_b), timeout_seconds=worker_timeout
        )
        received_b = _one_way_loopback(
            master_a,
            master_b,
            payload,
            settle_seconds=args.settle,
            result_timeout=worker_timeout + 1.0,
        )
        if received_b != payload:
            raise RuntimeError(
                "RS-485 loopback A->B mismatch: "
                f"sent {payload.hex(' ')}, received {received_b.hex(' ')}"
            )

        time.sleep(max(args.settle, 0.05))
        received_a = _one_way_loopback(
            master_b,
            master_a,
            payload,
            settle_seconds=args.settle,
            result_timeout=worker_timeout + 1.0,
        )
        if received_a != payload:
            raise RuntimeError(
                "RS-485 loopback B->A mismatch: "
                f"sent {payload.hex(' ')}, received {received_a.hex(' ')}"
            )

        return {
            "ok": True,
            "ports": {"a": args.port_a, "b": args.port_b},
            "settings": {
                "baudrate": args.baudrate,
                "parity": args.parity,
                "stopbits": args.stopbits,
                "bytesize": args.bytesize,
                "timeout_seconds": args.timeout,
            },
            "payload_hex": payload.hex(" "),
            "a_to_b": {"received_hex": received_b.hex(" "), "matched": True},
            "b_to_a": {"received_hex": received_a.hex(" "), "matched": True},
            "transmitted": True,
        }
    finally:
        if master_b is not None:
            master_b.close()
        master_a.close()


def _read_registers(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "read-holding":
        function = 0x03
        build_request: Callable[[int, int, int], bytes] = (
            build_read_holding_registers_request
        )
        parse_response = parse_read_holding_registers_response
    else:
        function = 0x04
        build_request = build_read_input_registers_request
        parse_response = parse_read_input_registers_response

    request = build_request(args.slave, args.address, args.count)
    master = ProcessRS485Master(
        _settings(args, args.port),
        timeout_seconds=max(3.0, args.timeout + 1.0),
    )
    try:
        response = master.transact(request)
    finally:
        master.close()
    registers = parse_response(
        response,
        expected_slave=args.slave,
        expected_count=args.count,
    )
    return {
        "ok": True,
        "port": args.port,
        "settings": {
            "baudrate": args.baudrate,
            "parity": args.parity,
            "stopbits": args.stopbits,
            "bytesize": args.bytesize,
            "timeout_seconds": args.timeout,
        },
        "slave": args.slave,
        "function": f"0x{function:02X}",
        "address": args.address,
        "count": args.count,
        "request_hex": request.hex(" "),
        "response_hex": response.hex(" "),
        "registers": registers,
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "ports":
            response = _ports_response()
        elif args.command == "check-ports":
            response = _check_ports(args)
        elif args.command == "loopback":
            response = _loopback(args)
        else:
            response = _read_registers(args)
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
    print(json.dumps(response, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
