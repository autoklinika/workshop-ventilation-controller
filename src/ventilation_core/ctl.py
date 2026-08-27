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
    subparsers.add_parser("sensors")
    subparsers.add_parser("aero")
    subparsers.add_parser("calendar")
    subparsers.add_parser("control-engine")

    calendar_replace = subparsers.add_parser("calendar-replace")
    calendar_replace.add_argument("--file", type=Path, required=True)

    control_engine_replace = subparsers.add_parser("control-engine-replace")
    control_engine_replace.add_argument("--file", type=Path, required=True)

    alerts = subparsers.add_parser("alerts")
    alerts.add_argument("--limit", type=int, default=200)

    ack_alert = subparsers.add_parser("ack-alert")
    ack_alert.add_argument("alert_id", type=int)

    aero_speed = subparsers.add_parser("aero-speed")
    aero_speed.add_argument("speed", type=int, choices=(0, 1, 2, 3))

    aero_airing = subparsers.add_parser("aero-airing")
    aero_airing.add_argument("state", choices=("on", "off"))

    set_command = subparsers.add_parser("set")
    set_command.add_argument("--supply", type=float, required=True)
    set_command.add_argument("--extract", type=float, required=True)
    subparsers.add_parser("stop")
    subparsers.add_parser("shutdown")
    return parser


def _read_one_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} file must contain one JSON object")
    return payload


def build_request(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "set":
        return {
            "command": "set",
            "supply_voltage": args.supply,
            "extract_voltage": args.extract,
        }
    if args.command == "calendar-replace":
        return {
            "command": "calendar-replace",
            "config": _read_one_json_object(args.file, label="Calendar"),
        }
    if args.command == "control-engine-replace":
        return {
            "command": "control-engine-replace",
            "config": _read_one_json_object(args.file, label="Control Engine"),
        }
    if args.command == "alerts":
        return {"command": "alerts", "limit": args.limit}
    if args.command == "ack-alert":
        return {"command": "ack-alert", "alert_id": args.alert_id}
    if args.command == "aero-speed":
        return {"command": "aero-speed", "speed": args.speed}
    if args.command == "aero-airing":
        return {"command": "aero-airing", "enabled": args.state == "on"}
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
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(response, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
