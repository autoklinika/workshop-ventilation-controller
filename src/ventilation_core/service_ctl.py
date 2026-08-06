from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Any

DEFAULT_SOCKET_PATH = Path("/run/wvc-service-agent/service-agent.sock")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local client for the CM5 service agent")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET_PATH)
    parser.add_argument("command", choices=("status", "nodes", "network"))
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


def main() -> int:
    args = build_parser().parse_args()
    try:
        response = send_request(args.socket, {"command": args.command})
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(response, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
