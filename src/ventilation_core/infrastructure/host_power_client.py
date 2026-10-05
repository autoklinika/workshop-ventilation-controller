from __future__ import annotations

import json
from pathlib import Path
import socket
from typing import Any


DEFAULT_HOST_POWER_SOCKET = Path("/run/wvc-host-power/host-power.sock")
MAX_RESPONSE_BYTES = 4096


class HostPowerError(RuntimeError):
    pass


class HostPowerClient:
    """Narrow Unix-socket client for the privileged host-power agent."""

    ACTIONS = ("shutdown", "restart")

    def __init__(
        self,
        socket_path: Path = DEFAULT_HOST_POWER_SOCKET,
        *,
        timeout_seconds: float = 165.0,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._timeout_seconds = float(timeout_seconds)

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def request(self, action: str) -> dict[str, Any]:
        if action not in self.ACTIONS:
            raise ValueError("unsupported host power action")

        payload = json.dumps({"action": action}, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout_seconds)
                client.connect(str(self._socket_path))
                client.sendall(payload)
                response = self._read_line(client)
        except (OSError, TimeoutError) as exc:
            raise HostPowerError(str(exc)) from exc

        try:
            decoded = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HostPowerError("invalid host-power agent response") from exc
        if not isinstance(decoded, dict):
            raise HostPowerError("invalid host-power agent response")
        return decoded

    @staticmethod
    def _read_line(client: socket.socket) -> bytes:
        data = bytearray()
        while len(data) < MAX_RESPONSE_BYTES:
            chunk = client.recv(min(512, MAX_RESPONSE_BYTES - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
        if not data:
            raise HostPowerError("empty host-power agent response")
        if len(data) >= MAX_RESPONSE_BYTES and b"\n" not in data:
            raise HostPowerError("host-power agent response too large")
        return bytes(data).split(b"\n", 1)[0]
