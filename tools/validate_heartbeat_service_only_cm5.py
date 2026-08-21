#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ventilation_core.alert_v2_stage4b_runtime import CoreReadOnlyClient, require_passive_safe_state
from ventilation_core.alert_v2_stage4c_fault import (
    HeartbeatDropRule,
    find_stage4c_handles,
    list_input_chain,
    validate_service_source_ip,
)
from ventilation_core.service_plane_monitor import read_service_agent_status


EXPECTED_NODE_MAPPING = {
    "sensor-node-1": 1,
    "sensor-node-2": 2,
}
HEARTBEAT_ALERT = "KAMOD_HEARTBEAT_LOST"
CORRELATED_NODE_ALERT = "KAMOD_NODE_UNAVAILABLE"
SERVICE_AGENT_SOCKET = Path("/run/wvc-service-agent/service-agent.sock")


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate on physical CM5 that heartbeat loss is service-only while "
            "the production SENSOR BUS remains healthy"
        )
    )
    parser.add_argument("--target-node", choices=tuple(EXPECTED_NODE_MAPPING), default="sensor-node-2")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--offline-timeout", type=float, default=60.0)
    parser.add_argument("--recovery-timeout", type=float, default=35.0)
    parser.add_argument("--settle-timeout", type=float, default=15.0)
    return parser


def _systemctl_value(unit: str, property_name: str) -> str:
    completed = subprocess.run(
        ["systemctl", "show", unit, "-p", property_name, "--value"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=3.0,
    )
    if completed.returncode != 0:
        raise ValidationError(
            f"systemctl show failed for {unit}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _require_active_pid(unit: str) -> int:
    completed = subprocess.run(
        ["systemctl", "is-active", "--quiet", unit],
        check=False,
        timeout=3.0,
    )
    if completed.returncode != 0:
        raise ValidationError(f"required service is not active: {unit}")
    raw = _systemctl_value(unit, "MainPID")
    try:
        pid = int(raw)
    except ValueError as exc:
        raise ValidationError(f"invalid MainPID for {unit}: {raw!r}") from exc
    if pid < 1:
        raise ValidationError(f"invalid MainPID for {unit}: {pid}")
    return pid


def _node_by_id(service: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = service.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError("Service Agent status missing nodes list")
    matches = [
        node for node in nodes
        if isinstance(node, dict) and node.get("node_id") == node_id
    ]
    if len(matches) != 1:
        raise ValidationError(f"expected exactly one {node_id}, got {len(matches)}")
    return matches[0]


def _require_service_network_healthy(service: dict[str, Any]) -> None:
    network = service.get("network")
    if not isinstance(network, dict):
        raise ValidationError("Service Agent status missing network")
    required = ("ready", "ap_active", "address_present", "dhcp_active", "firewall_active")
    bad = [field for field in required if network.get(field) is not True]
    if bad:
        raise ValidationError(f"WVC-SERVICE is not healthy: {bad}")


def _sensor_nodes_from_status(status: dict[str, Any]) -> dict[int, dict[str, Any]]:
    state = status.get("state")
    sensor_bus = state.get("sensor_bus") if isinstance(state, dict) else None
    if not isinstance(sensor_bus, dict):
        raise ValidationError("production core status missing SENSOR BUS")
    if sensor_bus.get("ready") is not True or sensor_bus.get("worker_alive") is not True:
        raise ValidationError("production SENSOR BUS is not ready/alive")
    nodes = sensor_bus.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError("production SENSOR BUS missing nodes list")
    result: dict[int, dict[str, Any]] = {}
    for item in nodes:
        if not isinstance(item, dict):
            continue
        address = item.get("slave_address")
        if isinstance(address, int) and not isinstance(address, bool):
            result[address] = item
    return result


def _capture_error_counters(nodes: dict[int, dict[str, Any]]) -> dict[int, dict[str, int]]:
    fields = (
        "communication_errors",
        "invalid_measurements",
        "stale_measurements",
        "map_version_errors",
    )
    result: dict[int, dict[str, int]] = {}
    for address in EXPECTED_NODE_MAPPING.values():
        node = nodes.get(address)
        if node is None:
            raise ValidationError(f"production SENSOR BUS missing slave {address}")
        if node.get("online") is not True or node.get("usable") is not True:
            raise ValidationError(f"production slave {address} is not online+usable")
        if node.get("measurement_valid") is not True or node.get("measurement_stale") is not False:
            raise ValidationError(f"production slave {address} measurement is not healthy")
        if node.get("consecutive_failures") != 0:
            raise ValidationError(f"production slave {address} has consecutive failures")
        counters: dict[str, int] = {}
        for field in fields:
            value = node.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(f"production slave {address} has invalid {field}")
            counters[field] = value
        result[address] = counters
    return result


def _require_error_counters_unchanged(
    baseline: dict[int, dict[str, int]],
    current_nodes: dict[int, dict[str, Any]],
) -> None:
    current = _capture_error_counters(current_nodes)
    for address, expected in baseline.items():
        if current[address] != expected:
            raise ValidationError(
                f"production SENSOR BUS counters changed for slave {address}: "
                f"{expected} -> {current[address]}"
            )


def _active_codes(client: CoreReadOnlyClient) -> set[str]:
    document = client.request("alerts", limit=200)
    active = document.get("active")
    if not isinstance(active, list):
        raise ValidationError("production alerts response missing active list")
    return {
        str(item.get("code"))
        for item in active
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }


def _alert_v2_correlation(status: dict[str, Any]) -> dict[str, Any]:
    state = status.get("state")
    alert_v2 = state.get("alert_v2") if isinstance(state, dict) else None
    service_plane = alert_v2.get("service_plane") if isinstance(alert_v2, dict) else None
    correlation = service_plane.get("correlation") if isinstance(service_plane, dict) else None
    if not isinstance(correlation, dict):
        raise ValidationError("production AlertV2 correlation diagnostics unavailable")
    if correlation.get("mode") != "read_only":
        raise ValidationError("production service-plane correlation is not read-only")
    if service_plane.get("control_policy_applied") is not False:
        raise ValidationError("service-plane correlation unexpectedly applies control policy")
    return correlation


def _require_no_heartbeat_operator_alert(client: CoreReadOnlyClient) -> None:
    codes = _active_codes(client)
    if HEARTBEAT_ALERT in codes:
        raise ValidationError(
            f"{HEARTBEAT_ALERT} became active despite healthy production SENSOR BUS"
        )
    if CORRELATED_NODE_ALERT in codes:
        raise ValidationError(
            f"{CORRELATED_NODE_ALERT} became active despite healthy production SENSOR BUS"
        )


def _require_runtime_safety(
    client: CoreReadOnlyClient,
    *,
    core_pid: int,
    agent_pid: int,
    baseline_counters: dict[int, dict[str, int]],
) -> dict[str, Any]:
    if _require_active_pid("ventilation-core.service") != core_pid:
        raise ValidationError("ventilation-core PID changed during validation")
    if _require_active_pid("wvc-service-agent.service") != agent_pid:
        raise ValidationError("Service Agent PID changed during validation")
    status = client.request("status")
    require_passive_safe_state(status)
    _require_error_counters_unchanged(
        baseline_counters,
        _sensor_nodes_from_status(status),
    )
    return status


def _install_signal_guards() -> None:
    def handler(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main() -> int:
    args = build_parser().parse_args()
    if os.geteuid() != 0:
        print("FAIL: run as root; validator installs one temporary nft rule", file=sys.stderr)
        return 2
    if (
        args.poll_interval <= 0
        or args.offline_timeout < 40
        or args.recovery_timeout <= 0
        or args.settle_timeout <= 0
    ):
        print("FAIL: invalid timing arguments", file=sys.stderr)
        return 2

    _install_signal_guards()
    target_node = args.target_node
    target_address = EXPECTED_NODE_MAPPING[target_node]
    other_node = next(node for node in EXPECTED_NODE_MAPPING if node != target_node)

    fault_rule: HeartbeatDropRule | None = None
    fault_installed = False
    handle: int | None = None
    offline_after: float | None = None
    recovery_after: float | None = None
    incidental_service_only_nodes: set[str] = set()

    try:
        stale = find_stage4c_handles(list_input_chain())
        if stale:
            raise ValidationError(f"stale heartbeat-drop nft rules exist: {stale}")

        core_pid = _require_active_pid("ventilation-core.service")
        agent_pid = _require_active_pid("wvc-service-agent.service")
        client = CoreReadOnlyClient(timeout_seconds=1.0)

        baseline_status = client.request("status")
        safety = require_passive_safe_state(baseline_status)
        baseline_counters = _capture_error_counters(_sensor_nodes_from_status(baseline_status))

        service = read_service_agent_status(SERVICE_AGENT_SOCKET, 0.35)
        _require_service_network_healthy(service)
        target = _node_by_id(service, target_node)
        other = _node_by_id(service, other_node)
        if target.get("online") is not True:
            raise ValidationError(f"target {target_node} heartbeat must be online before fault injection")
        if other.get("online") is not True:
            incidental_service_only_nodes.add(other_node)
        if target.get("modbus_address") != target_address:
            raise ValidationError(
                f"{target_node} mapping mismatch: expected Modbus {target_address}, "
                f"got {target.get('modbus_address')!r}"
            )
        if other.get("modbus_address") != EXPECTED_NODE_MAPPING[other_node]:
            raise ValidationError(f"{other_node} mapping mismatch")
        source_ip = target.get("source_ip")
        if not isinstance(source_ip, str):
            raise ValidationError(f"{target_node} has no source_ip")
        source_ip = validate_service_source_ip(source_ip)

        # Give the freshly restarted branch runtime enough time to reconcile and
        # clear any legacy active KAMOD_HEARTBEAT_LOST record from main.
        settle_deadline = time.monotonic() + args.settle_timeout
        while True:
            status = _require_runtime_safety(
                client,
                core_pid=core_pid,
                agent_pid=agent_pid,
                baseline_counters=baseline_counters,
            )
            codes = _active_codes(client)
            if HEARTBEAT_ALERT not in codes:
                break
            if time.monotonic() >= settle_deadline:
                raise ValidationError(
                    f"legacy {HEARTBEAT_ALERT} did not clear after branch deployment"
                )
            time.sleep(args.poll_interval)

        correlation = _alert_v2_correlation(status)
        if correlation.get("control_policy_applied") not in {None, False}:
            raise ValidationError("correlation unexpectedly applies control policy")

        fault_rule = HeartbeatDropRule.create(source_ip)
        handle = fault_rule.install()
        fault_installed = True
        started = time.monotonic()
        print(
            f"INFO: temporary heartbeat drop installed for {target_node} "
            f"source_ip={source_ip} handle={handle}",
            flush=True,
        )

        offline_deadline = started + args.offline_timeout
        proven_offline = False
        while time.monotonic() < offline_deadline:
            status = _require_runtime_safety(
                client,
                core_pid=core_pid,
                agent_pid=agent_pid,
                baseline_counters=baseline_counters,
            )
            fault_rule.verify_installed()
            service = read_service_agent_status(SERVICE_AGENT_SOCKET, 0.35)
            _require_service_network_healthy(service)
            target_now = _node_by_id(service, target_node)
            other_now = _node_by_id(service, other_node)
            if other_now.get("online") is not True:
                incidental_service_only_nodes.add(other_node)
            _require_no_heartbeat_operator_alert(client)
            if target_now.get("online") is False:
                correlation = _alert_v2_correlation(status)
                offline_nodes = correlation.get("service_only_offline_nodes")
                if not isinstance(offline_nodes, list) or target_node not in offline_nodes:
                    raise ValidationError(
                        f"{target_node} missing from service_only_offline_nodes: {offline_nodes!r}"
                    )
                derived_codes = correlation.get("derived_codes")
                if isinstance(derived_codes, list) and HEARTBEAT_ALERT in derived_codes:
                    raise ValidationError("heartbeat alert still appears in derived_codes")
                offline_after = time.monotonic() - started
                proven_offline = True
                break
            time.sleep(args.poll_interval)

        if not proven_offline:
            raise ValidationError(
                f"{target_node} did not become heartbeat-offline within {args.offline_timeout:.1f}s"
            )

        fault_rule.remove()
        fault_installed = False
        recovery_started = time.monotonic()
        print(
            f"INFO: heartbeat drop removed after {offline_after:.3f}s; waiting for recovery",
            flush=True,
        )

        recovery_deadline = recovery_started + args.recovery_timeout
        while time.monotonic() < recovery_deadline:
            status = _require_runtime_safety(
                client,
                core_pid=core_pid,
                agent_pid=agent_pid,
                baseline_counters=baseline_counters,
            )
            service = read_service_agent_status(SERVICE_AGENT_SOCKET, 0.35)
            _require_service_network_healthy(service)
            target_now = _node_by_id(service, target_node)
            other_now = _node_by_id(service, other_node)
            if other_now.get("online") is not True:
                incidental_service_only_nodes.add(other_node)
            _require_no_heartbeat_operator_alert(client)
            if target_now.get("online") is True:
                correlation = _alert_v2_correlation(status)
                offline_nodes = correlation.get("service_only_offline_nodes")
                if isinstance(offline_nodes, list) and target_node not in offline_nodes:
                    recovery_after = time.monotonic() - recovery_started
                    break
            time.sleep(args.poll_interval)

        if recovery_after is None:
            raise ValidationError(
                f"{target_node} did not recover cleanly within {args.recovery_timeout:.1f}s"
            )

        _require_runtime_safety(
            client,
            core_pid=core_pid,
            agent_pid=agent_pid,
            baseline_counters=baseline_counters,
        )
        _require_no_heartbeat_operator_alert(client)
        if find_stage4c_handles(list_input_chain()):
            raise ValidationError("temporary heartbeat-drop nft rule remains after validation")

        result = {
            "result": "PASS",
            "target": {
                "node_id": target_node,
                "modbus_address": target_address,
                "source_ip": source_ip,
            },
            "fault": {
                "temporary_nft_handle": handle,
                "heartbeat_offline_after_s": round(float(offline_after), 3),
                "heartbeat_recovered_after_s": round(float(recovery_after), 3),
                "operator_heartbeat_alert": False,
                "service_only_diagnostic": True,
                "incidental_service_only_nodes_observed": sorted(incidental_service_only_nodes),
            },
            "production": {
                "core_pid": core_pid,
                "service_agent_pid": agent_pid,
                "mode": safety.mode,
                "supply_voltage": safety.supply_voltage,
                "extract_voltage": safety.extract_voltage,
                "output_state_known": safety.output_state_known,
                "sensor_bus_error_counters_unchanged": True,
            },
            "safety": {
                "control_commands_sent_by_validator": 0,
                "control_policy_applied": False,
                "temporary_firewall_rule_removed": True,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        print("PASS: heartbeat loss is service-only while SENSOR BUS remains healthy")
        print(f"PASS: {HEARTBEAT_ALERT} was not emitted")
        print(f"PASS: {CORRELATED_NODE_ALERT} was not emitted without production failure")
        print("PASS: production SENSOR BUS stayed online/usable with unchanged error counters")
        if incidental_service_only_nodes:
            print(
                "PASS: incidental non-target heartbeat dropout remained service-only: "
                + ", ".join(sorted(incidental_service_only_nodes))
            )
        print("PASS: temporary nft rule removed and target heartbeat recovered")
        print("PASS: validator sent zero control commands")
        return 0
    except (ValidationError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if fault_installed and fault_rule is not None:
            try:
                fault_rule.remove()
                print("INFO: temporary heartbeat-drop rule removed in finally", file=sys.stderr)
            except Exception as cleanup_exc:  # pragma: no cover - physical cleanup path
                print(
                    f"CRITICAL CLEANUP FAILURE: remove temporary nft rule manually: {cleanup_exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
