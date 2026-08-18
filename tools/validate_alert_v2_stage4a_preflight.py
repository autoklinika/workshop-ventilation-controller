#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import time
from pathlib import Path
from typing import Any

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.service_plane_alert_registry import (
    ServicePlaneCorrelatingAlertRegistry,
)
from ventilation_core.service_plane_monitor import (
    DEFAULT_SERVICE_AGENT_SOCKET,
    ServicePlaneMonitor,
    read_service_agent_status,
)

DEFAULT_CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
MAX_CORE_RESPONSE_BYTES = 2 * 1024 * 1024
EXPECTED_NODE_MAPPING = {
    "sensor-node-1": 1,
    "sensor-node-2": 2,
}


class ValidationError(RuntimeError):
    pass


def _request_core(
    socket_path: Path,
    request: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    command = request.get("command")
    if command not in {"status", "sensors"}:
        raise ValidationError(f"Stage 4A allows read-only core commands only, got {command!r}")
    if timeout_seconds <= 0:
        raise ValidationError("core timeout must be positive")

    payload = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout_seconds)
        client.connect(str(socket_path))
        client.sendall(payload)
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_CORE_RESPONSE_BYTES:
                raise ValidationError("core response exceeds Stage 4A size limit")

    if not response:
        raise ValidationError("core closed connection without response")
    try:
        decoded = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid core JSON response: {exc}") from exc
    if not isinstance(decoded, dict) or decoded.get("ok") is not True:
        raise ValidationError(f"core request failed: {decoded!r}")
    return decoded


def _timed(callable_: Any, *args: Any) -> tuple[Any, float]:
    started = time.perf_counter_ns()
    result = callable_(*args)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    return result, elapsed_ms


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValidationError("latency sample list is empty")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(statistics.fmean(values), 3),
        "p50_ms": round(_percentile(values, 0.50), 3),
        "p95_ms": round(_percentile(values, 0.95), 3),
        "max_ms": round(max(values), 3),
    }


def _require_stop_zero(status: dict[str, Any]) -> None:
    state = status.get("state")
    if not isinstance(state, dict):
        raise ValidationError("core status is missing state")
    setpoints = state.get("setpoints")
    if not isinstance(setpoints, dict):
        raise ValidationError("core status is missing setpoints")
    if state.get("mode") != "STOP":
        raise ValidationError(f"Stage 4A requires mode=STOP, got {state.get('mode')!r}")
    supply = setpoints.get("supply_voltage")
    extract = setpoints.get("extract_voltage")
    if supply != 0.0 or extract != 0.0:
        raise ValidationError(
            f"Stage 4A requires 0 V / 0 V, got supply={supply!r} extract={extract!r}"
        )
    if state.get("output_state_known") is not True:
        raise ValidationError("Stage 4A requires output_state_known=true")


def _service_mapping(service: dict[str, Any]) -> dict[str, int]:
    agent = service.get("agent")
    network = service.get("network")
    nodes = service.get("nodes")
    if not isinstance(agent, dict) or agent.get("ready") is not True:
        raise ValidationError("Service Agent is not ready")
    if not isinstance(network, dict) or network.get("ready") is not True:
        raise ValidationError(f"WVC-SERVICE network is not ready: {network!r}")
    if not isinstance(nodes, list):
        raise ValidationError("Service Agent nodes list is missing")

    mapping: dict[str, int] = {}
    for raw in nodes:
        if not isinstance(raw, dict):
            raise ValidationError("Service Agent node entry is not an object")
        node_id = raw.get("node_id")
        address = raw.get("modbus_address")
        if not isinstance(node_id, str) or not node_id:
            raise ValidationError("Service Agent node_id is invalid")
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValidationError(f"Service Agent {node_id} has invalid Modbus address")
        if raw.get("online") is not True:
            raise ValidationError(f"Service Agent {node_id} is offline")
        if raw.get("rs485_ready") is not True:
            raise ValidationError(f"Service Agent {node_id} reports rs485_ready != true")
        if raw.get("modbus_monitor_ready") is not True:
            raise ValidationError(
                f"Service Agent {node_id} reports modbus_monitor_ready != true"
            )
        mapping[node_id] = address

    if mapping != EXPECTED_NODE_MAPPING:
        raise ValidationError(
            f"unexpected Service Agent mapping: {mapping!r}; expected {EXPECTED_NODE_MAPPING!r}"
        )
    return mapping


def _sensor_addresses(sensors: dict[str, Any]) -> list[int]:
    sensor_bus = sensors.get("sensor_bus")
    if not isinstance(sensor_bus, dict):
        raise ValidationError("core sensors response is missing sensor_bus")
    if sensor_bus.get("worker_alive") is not True or sensor_bus.get("ready") is not True:
        raise ValidationError(f"SENSOR BUS is not healthy: {sensor_bus!r}")
    nodes = sensor_bus.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError("SENSOR BUS node list is missing")

    addresses: list[int] = []
    for raw in nodes:
        if not isinstance(raw, dict):
            raise ValidationError("SENSOR BUS node entry is not an object")
        address = raw.get("slave_address")
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValidationError("SENSOR BUS slave_address is invalid")
        if raw.get("online") is not True or raw.get("usable") is not True:
            raise ValidationError(f"SENSOR BUS slave {address} is not online+usable")
        addresses.append(address)
    addresses.sort()
    if addresses != [1, 2]:
        raise ValidationError(f"unexpected SENSOR BUS addresses: {addresses!r}")
    return addresses


def _validate_branch_correlation_read_only(
    service_socket: Path,
    service_timeout: float,
) -> dict[str, Any]:
    monitor = ServicePlaneMonitor(service_socket, timeout_seconds=service_timeout)
    registry = ServicePlaneCorrelatingAlertRegistry(
        AlertRegistry(MemoryAlertStore()),
        monitor,
        agent_failure_threshold=3,
        node_initial_grace_seconds=40.0,
    )
    try:
        active = registry.reconcile([])
        diagnostics = registry.diagnostics()
    finally:
        registry.close()

    if active:
        raise ValidationError(
            "healthy live Service Plane unexpectedly produced derived AlertV2 records: "
            + ", ".join(record.code.value for record in active)
        )
    if diagnostics.get("control_policy_applied") is not False:
        raise ValidationError("Stage 4A correlation diagnostics lost read-only invariant")
    correlation = diagnostics.get("correlation")
    if not isinstance(correlation, dict):
        raise ValidationError("Stage 4A correlation diagnostics are missing")
    if correlation.get("control_policy_applied") is not False:
        raise ValidationError("Stage 4A correlator claims control policy was applied")
    if correlation.get("derived_codes"):
        raise ValidationError(
            f"healthy live Service Plane produced derived codes: {correlation.get('derived_codes')!r}"
        )
    return {
        "mode": correlation.get("mode"),
        "reason": correlation.get("reason"),
        "derived_codes": correlation.get("derived_codes"),
        "control_policy_applied": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AlertV2 Stage 4A passive CM5 preflight. Reads production core and "
            "Service Agent only; never sends actuation, ACK, OTA or configuration commands."
        )
    )
    parser.add_argument("--core-socket", type=Path, default=DEFAULT_CORE_SOCKET)
    parser.add_argument(
        "--service-agent-socket",
        type=Path,
        default=DEFAULT_SERVICE_AGENT_SOCKET,
    )
    parser.add_argument("--core-timeout", type=float, default=1.0)
    parser.add_argument("--service-timeout", type=float, default=0.35)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.25)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 3 <= args.samples <= 300:
        raise SystemExit("FAIL: --samples must be in range 3..300")
    if args.interval < 0 or args.interval > 10:
        raise SystemExit("FAIL: --interval must be in range 0..10 seconds")
    if args.core_timeout <= 0 or args.service_timeout <= 0:
        raise SystemExit("FAIL: timeouts must be positive")

    core_latencies: list[float] = []
    service_latencies: list[float] = []

    try:
        initial_status = _request_core(
            args.core_socket,
            {"command": "status"},
            args.core_timeout,
        )
        _require_stop_zero(initial_status)
        initial_sensors = _request_core(
            args.core_socket,
            {"command": "sensors"},
            args.core_timeout,
        )
        addresses = _sensor_addresses(initial_sensors)
        initial_service = read_service_agent_status(
            args.service_agent_socket,
            args.service_timeout,
        )
        mapping = _service_mapping(initial_service)

        correlation = _validate_branch_correlation_read_only(
            args.service_agent_socket,
            args.service_timeout,
        )

        for index in range(args.samples):
            status, core_ms = _timed(
                _request_core,
                args.core_socket,
                {"command": "status"},
                args.core_timeout,
            )
            _require_stop_zero(status)
            core_latencies.append(core_ms)

            service, service_ms = _timed(
                read_service_agent_status,
                args.service_agent_socket,
                args.service_timeout,
            )
            _service_mapping(service)
            service_latencies.append(service_ms)

            if index + 1 < args.samples and args.interval:
                time.sleep(args.interval)

        final_status = _request_core(
            args.core_socket,
            {"command": "status"},
            args.core_timeout,
        )
        _require_stop_zero(final_status)
        final_sensors = _request_core(
            args.core_socket,
            {"command": "sensors"},
            args.core_timeout,
        )
        _sensor_addresses(final_sensors)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    summary = {
        "stage": "AlertV2 Stage 4A passive runtime preflight",
        "result": "PASS",
        "samples": args.samples,
        "core_socket": str(args.core_socket),
        "service_agent_socket": str(args.service_agent_socket),
        "node_mapping": mapping,
        "sensor_bus_addresses": addresses,
        "core_latency": _latency_summary(core_latencies),
        "service_agent_latency": _latency_summary(service_latencies),
        "correlation": correlation,
        "safety": {
            "required_mode": "STOP",
            "required_setpoints_v": {"supply": 0.0, "extract": 0.0},
            "write_commands_sent": 0,
            "control_policy_applied": False,
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    print("PASS: AlertV2 Stage 4A passive CM5 preflight completed")
    print("PASS: production core remained STOP / 0 V throughout validation")
    print("PASS: sensor-node-1/2 map exactly to Modbus 1/2")
    print("PASS: live Service Plane correlation stayed diagnostic/read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
