from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Protocol


class CoreClientError(RuntimeError):
    """Raised when the web service cannot exchange a valid response with ventilation-core."""


class CoreClient(Protocol):
    def request(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class CoreUnixClient:
    """Small JSON-lines client for the authoritative ventilation-core Unix socket."""

    MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def __init__(self, socket_path: Path, timeout_seconds: float = 70.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Core client timeout must be positive")
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        response = bytearray()

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout_seconds)
                client.connect(str(self._socket_path))
                client.sendall(encoded)
                while not response.endswith(b"\n"):
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if len(response) > self.MAX_RESPONSE_BYTES:
                        raise CoreClientError("ventilation-core response exceeds safety limit")
        except (OSError, TimeoutError) as exc:
            raise CoreClientError(f"ventilation-core unavailable: {exc}") from exc

        if not response:
            raise CoreClientError("ventilation-core returned an empty response")

        try:
            decoded = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoreClientError("ventilation-core returned invalid JSON") from exc

        if not isinstance(decoded, dict):
            raise CoreClientError("ventilation-core response must be a JSON object")
        return decoded
