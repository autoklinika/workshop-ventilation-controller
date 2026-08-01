from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local client for ventilation-core")
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path("/run/workshop-ventilation/ventilation-core.sock"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    set_command = subparsers.add_parser("set")
    set_command.add_argument("--supply", type=float, required=True)
    set_command.add_argument("--extract", type=float, required=True)
    subparsers.add_parser("stop")
    subparsers.add_parser("shutdown")
    return parser


def build_request(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "set":
        return {
            "command": "set",
            "supply_voltage": args.supply,
            "extract_voltage": args.extract,
        }
    return {"command": args.command}


def send_request(socket_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
    return json.loads(response.decode("utf-8"))


def main() -> int:
    args = build_parser().parse_args()
    try:
        response = send_request(args.socket, build_request(args))
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(response, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
