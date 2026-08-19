from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable


DEFAULT_SERVICE_AGENT_SOCKET = Path("/run/wvc-service-agent/service-agent.sock")
MAX_RESPONSE_BYTES = 256 * 1024


class ServicePlaneMonitorError(RuntimeError):
    pass


def read_service_agent_status(
    socket_path: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("service agent timeout must be positive")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout_seconds)
        client.connect(str(socket_path))
        client.sendall(b'{"command":"status"}\n')
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_RESPONSE_BYTES:
                raise ServicePlaneMonitorError("service agent response exceeds size limit")

    if not response:
        raise ServicePlaneMonitorError("service agent closed connection without response")
    try:
        decoded = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServicePlaneMonitorError(f"invalid service agent JSON response: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ServicePlaneMonitorError("service agent response must be an object")
    if decoded.get("ok") is not True:
        raise ServicePlaneMonitorError(
            f"service agent rejected status request: {decoded.get('error', 'unknown error')}"
        )
    if not isinstance(decoded.get("agent"), dict):
        raise ServicePlaneMonitorError("service agent response missing agent object")
    if not isinstance(decoded.get("network"), dict):
        raise ServicePlaneMonitorError("service agent response missing network object")
    if not isinstance(decoded.get("nodes"), list):
        raise ServicePlaneMonitorError("service agent response missing nodes list")
    return decoded


@dataclass(frozen=True)
class ServicePlaneMonitorState:
    available: bool
    consecutive_failures: int
    last_error: str | None
    last_attempt_unix_ms: int | None
    last_success_unix_ms: int | None
    snapshot: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_attempt_unix_ms": self.last_attempt_unix_ms,
            "last_success_unix_ms": self.last_success_unix_ms,
            "snapshot": self.snapshot,
        }


class ServicePlaneMonitor:
    """Non-authoritative reader of the independent WVC-SERVICE agent.

    The monitor never opens SENSOR BUS, never controls hardware and never writes
    to Service Agent.  ``poll`` performs one bounded local read and preserves
    the last successful snapshot for diagnostics.
    """

    def __init__(
        self,
        socket_path: str | Path = DEFAULT_SERVICE_AGENT_SOCKET,
        *,
        timeout_seconds: float = 0.35,
        requester: Callable[[Path, float], dict[str, Any]] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("service agent timeout must be positive")
        self._socket_path = Path(socket_path)
        self._timeout_seconds = float(timeout_seconds)
        self._requester = requester or read_service_agent_status
        self._lock = RLock()
        self._available = False
        self._consecutive_failures = 0
        self._last_error: str | None = None
        self._last_attempt_unix_ms: int | None = None
        self._last_success_unix_ms: int | None = None
        self._snapshot: dict[str, Any] | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def poll(self) -> ServicePlaneMonitorState:
        attempted = int(time.time() * 1000)
        try:
            response = self._requester(self._socket_path, self._timeout_seconds)
        except Exception as exc:
            with self._lock:
                self._available = False
                self._consecutive_failures += 1
                self._last_error = str(exc)
                self._last_attempt_unix_ms = attempted
                return self._state_locked()

        with self._lock:
            self._available = True
            self._consecutive_failures = 0
            self._last_error = None
            self._last_attempt_unix_ms = attempted
            self._last_success_unix_ms = attempted
            self._snapshot = response
            return self._state_locked()

    def state(self) -> ServicePlaneMonitorState:
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> ServicePlaneMonitorState:
        snapshot = None if self._snapshot is None else dict(self._snapshot)
        if snapshot is not None:
            nodes = snapshot.get("nodes")
            if isinstance(nodes, list):
                snapshot["nodes"] = [dict(node) if isinstance(node, dict) else node for node in nodes]
            network = snapshot.get("network")
            if isinstance(network, dict):
                snapshot["network"] = dict(network)
            agent = snapshot.get("agent")
            if isinstance(agent, dict):
                snapshot["agent"] = dict(agent)
        return ServicePlaneMonitorState(
            available=self._available,
            consecutive_failures=self._consecutive_failures,
            last_error=self._last_error,
            last_attempt_unix_ms=self._last_attempt_unix_ms,
            last_success_unix_ms=self._last_success_unix_ms,
            snapshot=snapshot,
        )
