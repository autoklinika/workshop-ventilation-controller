from __future__ import annotations

import argparse
import json
from typing import Any

from ventilation_core.rs485.modbus import (
    build_read_holding_registers_request,
    parse_read_holding_registers_response,
)
from ventilation_core.rs485.ports import discover_serial_ports
from ventilation_core.rs485.serial_transport import SerialSettings
from ventilation_core.rs485.worker import ProcessRS485Master


def _integer(value: str) -> int:
    return int(value, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RS-485 / Modbus RTU bring-up tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ports", help="list detected USB serial interfaces")

    read = subparsers.add_parser(
        "read-holding", help="read Modbus holding registers (function 0x03)"
    )
    read.add_argument("--port", required=True)
    read.add_argument("--baudrate", type=int, default=9600)
    read.add_argument("--parity", choices=("N", "E", "O"), default="N")
    read.add_argument("--stopbits", type=int, choices=(1, 2), default=1)
    read.add_argument("--bytesize", type=int, choices=(7, 8), default=8)
    read.add_argument("--timeout", type=float, default=0.5)
    read.add_argument("--slave", type=_integer, required=True)
    read.add_argument("--address", type=_integer, required=True)
    read.add_argument("--count", type=int, default=1)
    return parser


def _ports_response() -> dict[str, Any]:
    ports = [port.to_dict() for port in discover_serial_ports()]
    return {"ok": True, "ports": ports, "count": len(ports)}


def _read_holding(args: argparse.Namespace) -> dict[str, Any]:
    settings = SerialSettings(
        port=args.port,
        baudrate=args.baudrate,
        parity=args.parity,
        stopbits=args.stopbits,
        bytesize=args.bytesize,
        timeout_seconds=args.timeout,
    )
    request = build_read_holding_registers_request(
        args.slave,
        args.address,
        args.count,
    )
    master = ProcessRS485Master(
        settings,
        timeout_seconds=max(3.0, args.timeout + 1.0),
    )
    try:
        response = master.transact(request)
    finally:
        master.close()
    registers = parse_read_holding_registers_response(
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
        "address": args.address,
        "count": args.count,
        "request_hex": request.hex(" "),
        "response_hex": response.hex(" "),
        "registers": registers,
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        response = _ports_response() if args.command == "ports" else _read_holding(args)
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
    print(json.dumps(response, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
