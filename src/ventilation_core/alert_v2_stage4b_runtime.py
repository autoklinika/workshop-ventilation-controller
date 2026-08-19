from __future__ import annotations

import json
import os
import socket
import socketserver
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ventilation_core.alert_policy_runtime import RuntimeAlertPolicyManager
from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.service_plane_alert_registry import (
    ServicePlaneCorrelatingAlertRegistry,
)
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity
from ventilation_core.service_plane_monitor import (
    DEFAULT_SERVICE_AGENT_SOCKET,
    ServicePlaneMonitor,
    read_service_agent_status,
)


DEFAULT_CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_STAGE4B_SOCKET = Path("/tmp/wvc-alert-v2-stage4b.sock")
READ_ONLY_CORE_COMMANDS = frozenset({"status", "alerts"})
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class Stage4BError(RuntimeError):
    pass


def request_unix_json(
    socket_path: Path,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout_seconds)
        client.connect(str(socket_path))
        client.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_RESPONSE_BYTES:
                raise Stage4BError("response exceeds size limit")
    if not response:
        raise Stage4BError(f"empty response from {socket_path}")
    try:
        decoded = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stage4BError(f"invalid JSON from {socket_path}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise Stage4BError("response must be a JSON object")
    return decoded


class CoreReadOnlyClient:
    def __init__(
        self,
        socket_path: Path = DEFAULT_CORE_SOCKET,
        *,
        timeout_seconds: float = 0.5,
        requester: Callable[[Path, dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._timeout_seconds = float(timeout_seconds)
        self._requester = requester or request_unix_json

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def request(self, command: str, **fields: Any) -> dict[str, Any]:
        if command not in READ_ONLY_CORE_COMMANDS:
            raise Stage4BError(f"Stage 4B forbids core command: {command}")
        request = {"command": command, **fields}
        started = time.perf_counter()
        response = self._requester(self._socket_path, request, self._timeout_seconds)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if response.get("ok") is not True:
            raise Stage4BError(
                f"production core {command} failed: {response.get('error', 'unknown error')}"
            )
        result = dict(response)
        result["_latency_ms"] = elapsed_ms
        return result


@dataclass(frozen=True)
class SafetySnapshot:
    mode: str
    supply_voltage: float
    extract_voltage: float
    output_state_known: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "setpoints_v": {
                "supply": self.supply_voltage,
                "extract": self.extract_voltage,
            },
            "output_state_known": self.output_state_known,
        }


def require_passive_safe_state(state_document: dict[str, Any]) -> SafetySnapshot:
    state = state_document.get("state")
    if not isinstance(state, dict):
        raise Stage4BError("production core status missing state")
    mode = state.get("mode")
    setpoints = state.get("setpoints")
    if not isinstance(setpoints, dict):
        raise Stage4BError("production core status missing setpoints")
    supply = setpoints.get("supply_voltage")
    extract = setpoints.get("extract_voltage")
    if isinstance(supply, bool) or not isinstance(supply, (int, float)):
        raise Stage4BError("invalid production supply setpoint")
    if isinstance(extract, bool) or not isinstance(extract, (int, float)):
        raise Stage4BError("invalid production extract setpoint")
    known = state.get("output_state_known") is True
    snapshot = SafetySnapshot(
        mode=str(mode),
        supply_voltage=float(supply),
        extract_voltage=float(extract),
        output_state_known=known,
    )
    if snapshot.mode != "STOP":
        raise Stage4BError(f"Stage 4B requires production mode STOP, got {snapshot.mode}")
    if snapshot.supply_voltage != 0.0 or snapshot.extract_voltage != 0.0:
        raise Stage4BError(
            "Stage 4B requires production setpoints 0.0 V / 0.0 V, got "
            f"{snapshot.supply_voltage} / {snapshot.extract_voltage}"
        )
    if not snapshot.output_state_known:
        raise Stage4BError("Stage 4B requires output_state_known=true")
    return snapshot


def active_payload_to_signal(payload: dict[str, Any]) -> AlertSignal:
    try:
        code = AlarmCode(str(payload["code"]))
        severity = AlarmSeverity(str(payload["severity"]))
    except (KeyError, ValueError) as exc:
        raise Stage4BError(f"unsupported production alert contract: {payload!r}") from exc
    key = payload.get("key")
    if not isinstance(key, str) or not key:
        # Core state does not expose keys, but the authoritative `alerts` command does.
        raise Stage4BError(f"production active alert {code.value} has no lifecycle key")
    source = payload.get("source")
    message = payload.get("message")
    if not isinstance(source, str) or not source:
        raise Stage4BError(f"production active alert {code.value} has invalid source")
    if not isinstance(message, str) or not message:
        raise Stage4BError(f"production active alert {code.value} has invalid message")
    detail = payload.get("detail")
    if not isinstance(detail, str):
        detail = ""
    occurrences = payload.get("occurrences", 1)
    if isinstance(occurrences, bool) or not isinstance(occurrences, int) or occurrences < 1:
        occurrences = 1
    return AlertSignal(
        key=key,
        code=code,
        source=source,
        severity=severity,
        message=message,
        detail=detail,
        occurrences=occurrences,
    )


class Stage4BShadowRuntime:
    """Live read-only AlertV2 projection over the production core.

    This process owns no hardware, no production database and no control API.
    It reads production `status`/`alerts`, reads Service Agent `status`, applies
    the real Stage 3 correlation and AlertV2 policy in memory, and exposes only
    a local read-only `status` socket for validation.
    """

    def __init__(
        self,
        *,
        policy_path: Path,
        core_socket: Path = DEFAULT_CORE_SOCKET,
        service_agent_socket: Path = DEFAULT_SERVICE_AGENT_SOCKET,
        core_timeout_seconds: float = 0.5,
        service_timeout_seconds: float = 0.35,
        service_requester: Callable[[Path, float], dict[str, Any]] | None = None,
        core_requester: Callable[[Path, dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self._core = CoreReadOnlyClient(
            core_socket,
            timeout_seconds=core_timeout_seconds,
            requester=core_requester,
        )
        self._policy = RuntimeAlertPolicyManager(policy_path)
        if not self._policy.loaded:
            raise Stage4BError(
                f"AlertV2 policy did not load: {self._policy.metadata().get('last_error')}"
            )
        monitor = ServicePlaneMonitor(
            service_agent_socket,
            timeout_seconds=service_timeout_seconds,
            requester=service_requester or read_service_agent_status,
        )
        self._registry = ServicePlaneCorrelatingAlertRegistry(
            AlertRegistry(MemoryAlertStore()),
            monitor,
        )
        self._lock = threading.RLock()
        self._latest: dict[str, Any] | None = None
        self._iterations = 0
        self._refresh_failures = 0
        self._last_error: str | None = None
        self._write_commands_sent = 0

    @property
    def write_commands_sent(self) -> int:
        return self._write_commands_sent

    def refresh(self) -> dict[str, Any]:
        started = time.perf_counter()
        status = self._core.request("status")
        safety = require_passive_safe_state(status)
        alerts_document = self._core.request("alerts", limit=200)
        active = alerts_document.get("active")
        if not isinstance(active, list):
            raise Stage4BError("production core alerts response missing active list")
        signals = tuple(
            active_payload_to_signal(item)
            for item in active
            if isinstance(item, dict)
        )
        correlated = self._registry.reconcile(signals)
        correlated_payloads = [record.to_dict() for record in correlated]
        decorated = [self._policy.decorate_alert_payload(item) for item in correlated_payloads]
        summary = self._policy.active_summary(correlated_payloads)
        if summary.get("unmapped_active_alerts") != 0:
            raise Stage4BError(
                f"AlertV2 policy has unmapped active alerts: {summary.get('unmapped_active_alerts')}"
            )
        diagnostics = self._registry.diagnostics()
        correlation = diagnostics.get("correlation")
        if not isinstance(correlation, dict):
            raise Stage4BError("Stage 3 correlation diagnostics unavailable")
        if diagnostics.get("control_policy_applied") is not False:
            raise Stage4BError("Stage 3 unexpectedly reports control policy applied")

        self._iterations += 1
        refresh_ms = (time.perf_counter() - started) * 1000.0
        snapshot = {
            "ok": True,
            "stage": "AlertV2 Stage 4B shadow runtime",
            "mode": "read_only_shadow",
            "updated_unix_ms": int(time.time() * 1000),
            "iteration": self._iterations,
            "safety": {
                **safety.to_dict(),
                "required_mode": "STOP",
                "required_setpoints_v": {"supply": 0.0, "extract": 0.0},
                "write_commands_sent": self._write_commands_sent,
                "control_policy_applied": False,
            },
            "sources": {
                "core_socket": str(self._core.socket_path),
                "core_status_latency_ms": round(float(status["_latency_ms"]), 3),
                "core_alerts_latency_ms": round(float(alerts_document["_latency_ms"]), 3),
                "service_agent_socket": str(self._registry.monitor.socket_path),
            },
            "policy": self._policy.metadata(),
            "alert_v2": summary,
            "active": decorated,
            "correlation": correlation,
            "service_plane": diagnostics.get("monitor"),
            "refresh_duration_ms": round(refresh_ms, 3),
            "refresh_failures": self._refresh_failures,
            "last_error": None,
        }
        with self._lock:
            self._latest = snapshot
            self._last_error = None
        return snapshot

    def record_refresh_failure(self, exc: BaseException) -> None:
        with self._lock:
            self._refresh_failures += 1
            self._last_error = str(exc)

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._latest is None:
                return {
                    "ok": False,
                    "stage": "AlertV2 Stage 4B shadow runtime",
                    "error": self._last_error or "runtime has no successful snapshot yet",
                    "write_commands_sent": self._write_commands_sent,
                    "control_policy_applied": False,
                }
            result = dict(self._latest)
            result["refresh_failures"] = self._refresh_failures
            result["last_error"] = self._last_error
            if self._last_error is not None:
                result["ok"] = False
            return result

    def close(self) -> None:
        self._registry.close()


class _Stage4BRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(65536)
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict) or request.get("command") != "status":
                response = {
                    "ok": False,
                    "error": "Stage 4B shadow runtime exposes read-only status only",
                }
            else:
                response = self.server.runtime.status()  # type: ignore[attr-defined]
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        self.wfile.write((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))


class _Stage4BUnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, path: str, runtime: Stage4BShadowRuntime) -> None:
        self.runtime = runtime
        super().__init__(path, _Stage4BRequestHandler)


def _remove_test_socket(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(mode):
        raise Stage4BError(f"refusing to remove non-socket path: {path}")
    path.unlink()


def serve_shadow_runtime(
    runtime: Stage4BShadowRuntime,
    *,
    listen_socket: Path = DEFAULT_STAGE4B_SOCKET,
    refresh_interval_seconds: float = 0.5,
    stop_event: threading.Event | None = None,
) -> None:
    if refresh_interval_seconds <= 0:
        raise ValueError("refresh interval must be positive")
    stop = stop_event or threading.Event()
    _remove_test_socket(listen_socket)
    runtime.refresh()

    server = _Stage4BUnixServer(str(listen_socket), runtime)
    os.chmod(listen_socket, 0o600)

    def refresh_loop() -> None:
        while not stop.wait(refresh_interval_seconds):
            try:
                runtime.refresh()
            except BaseException as exc:
                runtime.record_refresh_failure(exc)

    worker = threading.Thread(target=refresh_loop, name="alert-v2-stage4b-refresh", daemon=True)
    worker.start()
    server.timeout = 0.25
    try:
        while not stop.is_set():
            server.handle_request()
    finally:
        stop.set()
        worker.join(timeout=2.0)
        server.server_close()
        runtime.close()
        _remove_test_socket(listen_socket)
