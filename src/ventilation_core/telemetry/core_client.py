from __future__ import annotations

import json
from pathlib import Path
import socket
from typing import Any


class CoreStateClient:
    """Read-only client for the existing ventilation-core Unix socket."""

    def __init__(self, socket_path: Path, timeout_seconds: float = 2.0) -> None:
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    def read_state(self) -> dict[str, Any]:
        request = {"command": "status"}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(self.timeout_seconds)
            client.connect(str(self.socket_path))
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))
            response = b""
            while not response.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    break
                response += chunk

        decoded = json.loads(response.decode("utf-8"))
        if not decoded.get("ok"):
            raise RuntimeError(str(decoded.get("error", "ventilation-core status failed")))
        state = decoded.get("state")
        if not isinstance(state, dict):
            raise RuntimeError("ventilation-core returned an invalid state payload")
        return state
