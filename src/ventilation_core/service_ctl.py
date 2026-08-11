from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path
from typing import Any

DEFAULT_SOCKET_PATH = Path("/run/wvc-service-agent/service-agent.sock")
TERMINAL_OTA_STATES = frozenset({"succeeded", "failed", "rolled_back", "uncertain"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local client for the CM5 service agent")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("status", "nodes", "network"):
        subparsers.add_parser(command)

    ota_status = subparsers.add_parser("ota-status")
    ota_status.add_argument("node_id")

    ota_install = subparsers.add_parser("ota-install")
    ota_install.add_argument("node_id")
    ota_install.add_argument("image", type=Path)
    ota_install.add_argument("--no-wait", action="store_true")
    ota_install.add_argument("--wait-timeout", type=int, default=300)
    return parser


def send_request(socket_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
    if not response:
        raise RuntimeError("service agent closed the connection without a response")
    decoded = json.loads(response.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("service agent returned a non-object response")
    return decoded


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _ota_state(response: dict[str, Any]) -> str | None:
    ota = response.get("ota")
    if not isinstance(ota, dict):
        return None
    operation = ota.get("operation")
    if not isinstance(operation, dict):
        return None
    state = operation.get("state")
    return state if isinstance(state, str) else None


def main() -> int:
    args = build_parser().parse_args()
    request: dict[str, Any] = {"command": args.command}
    if args.command == "ota-status":
        request["node_id"] = args.node_id
    elif args.command == "ota-install":
        request["node_id"] = args.node_id
        request["image_path"] = str(args.image.expanduser().resolve(strict=False))

    try:
        response = send_request(args.socket, request)
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    _print(response)
    if response.get("ok") is not True:
        return 1

    if args.command != "ota-install" or args.no_wait:
        return 0

    deadline = time.monotonic() + max(1, args.wait_timeout)
    last_state = _ota_state(response)
    while last_state not in TERMINAL_OTA_STATES:
        if time.monotonic() >= deadline:
            _print(
                {
                    "ok": False,
                    "error": "timed out waiting for OTA completion; use ota-status to continue monitoring",
                    "last_state": last_state,
                }
            )
            return 3
        time.sleep(2.0)
        try:
            response = send_request(
                args.socket,
                {"command": "ota-status", "node_id": args.node_id},
            )
        except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _print({"ok": False, "error": str(exc)})
            return 2
        current_state = _ota_state(response)
        if current_state != last_state:
            _print(response)
            last_state = current_state

    if last_state == "succeeded":
        return 0
    _print(response)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
