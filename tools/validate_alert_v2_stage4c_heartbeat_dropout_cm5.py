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

from ventilation_core.alert_v2_stage4b_runtime import (
    CoreReadOnlyClient,
    Stage4BShadowRuntime,
    require_passive_safe_state,
)
from ventilation_core.alert_v2_stage4c_fault import (
    HeartbeatDropRule,
    Stage4CFaultError,
    find_stage4c_handles,
    list_input_chain,
    validate_service_source_ip,
)
from ventilation_core.service_plane_monitor import read_service_agent_status


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "config" / "alerts-v2.default.toml"
EXPECTED_NODE_MAPPING = {
    "sensor-node-1": 1,
    "sensor-node-2": 2,
}
TARGET_ALERT = "KAMOD_HEARTBEAT_LOST"


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AlertV2 Stage 4C heartbeat-only fault injection on CM5"
    )
    parser.add_argument("--target-node", choices=tuple(EXPECTED_NODE_MAPPING), default="sensor-node-1")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--offline-timeout", type=float, default=55.0)
    parser.add_argument("--recovery-timeout", type=float, default=30.0)
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
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", unit],
        check=False,
        timeout=3.0,
    )
    if active.returncode != 0:
        raise ValidationError(f"required production service is not active: {unit}")
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
    matches = [node for node in nodes if isinstance(node, dict) and node.get("node_id") == node_id]
    if len(matches) != 1:
        raise ValidationError(f"Service Agent expected exactly one {node_id}, got {len(matches)}")
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
        counters: dict[str, int] = {}
        if node.get("online") is not True or node.get("usable") is not True:
            raise ValidationError(f"production slave {address} is not online+usable")
        if node.get("measurement_valid") is not True or node.get("measurement_stale") is not False:
            raise ValidationError(f"production slave {address} measurement is not healthy")
        if node.get("consecutive_failures") != 0:
            raise ValidationError(f"production slave {address} has consecutive failures")
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
                f"production SENSOR BUS error counters changed for slave {address}: "
                f"{expected} -> {current[address]}"
            )


def _require_runtime_safety(
    core: CoreReadOnlyClient,
    *,
    expected_core_pid: int,
    expected_agent_pid: int,
    baseline_counters: dict[int, dict[str, int]],
) -> dict[str, Any]:
    if _require_active_pid("ventilation-core.service") != expected_core_pid:
        raise ValidationError("production ventilation-core PID changed during Stage 4C")
    if _require_active_pid("wvc-service-agent.service") != expected_agent_pid:
        raise ValidationError("production Service Agent PID changed during Stage 4C")
    status = core.request("status")
    require_passive_safe_state(status)
    _require_error_counters_unchanged(baseline_counters, _sensor_nodes_from_status(status))
    return status


def _find_public_node(snapshot: dict[str, Any], node_id: str) -> dict[str, Any]:
    service_plane = snapshot.get("service_plane")
    nodes = service_plane.get("nodes") if isinstance(service_plane, dict) else None
    if not isinstance(nodes, list):
        raise ValidationError("shadow runtime missing service-plane node diagnostics")
    matches = [node for node in nodes if isinstance(node, dict) and node.get("node_id") == node_id]
    if len(matches) != 1:
        raise ValidationError(f"shadow runtime expected exactly one {node_id}")
    return matches[0]


def _active_by_code(snapshot: dict[str, Any], code: str) -> list[dict[str, Any]]:
    active = snapshot.get("active")
    if not isinstance(active, list):
        raise ValidationError("shadow runtime missing active alert list")
    return [item for item in active if isinstance(item, dict) and item.get("code") == code]


def _install_signal_guards() -> None:
    def handler(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main() -> int:
    args = build_parser().parse_args()
    if os.geteuid() != 0:
        print("FAIL: Stage 4C must run as root because it installs one temporary nft rule", file=sys.stderr)
        return 2
    if args.poll_interval <= 0 or args.offline_timeout < 40 or args.recovery_timeout <= 0:
        print("FAIL: invalid Stage 4C timing arguments", file=sys.stderr)
        return 2

    _install_signal_guards()
    target_node = args.target_node
    target_address = EXPECTED_NODE_MAPPING[target_node]
    other_node = next(node for node in EXPECTED_NODE_MAPPING if node != target_node)

    runtime: Stage4BShadowRuntime | None = None
    fault_rule: HeartbeatDropRule | None = None
    fault_installed = False
    offline_detected_after: float | None = None
    recovered_after: float | None = None
    rule_handle: int | None = None

    try:
        stale_handles = find_stage4c_handles(list_input_chain())
        if stale_handles:
            raise ValidationError(
                f"stale Stage 4C nft rules exist before test; remove manually first: {stale_handles}"
            )

        core_pid = _require_active_pid("ventilation-core.service")
        agent_pid = _require_active_pid("wvc-service-agent.service")
        core = CoreReadOnlyClient()
        baseline_status = core.request("status")
        safety = require_passive_safe_state(baseline_status)
        baseline_counters = _capture_error_counters(_sensor_nodes_from_status(baseline_status))

        service = read_service_agent_status(
            Path("/run/wvc-service-agent/service-agent.sock"), 0.35
        )
        _require_service_network_healthy(service)
        target = _node_by_id(service, target_node)
        other = _node_by_id(service, other_node)
        if target.get("online") is not True or other.get("online") is not True:
            raise ValidationError("both KAmod service heartbeats must be online before Stage 4C")
        if target.get("modbus_address") != target_address:
            raise ValidationError(
                f"{target_node} mapping mismatch: expected Modbus {target_address}, "
                f"got {target.get('modbus_address')!r}"
            )
        if other.get("modbus_address") != EXPECTED_NODE_MAPPING[other_node]:
            raise ValidationError(f"{other_node} mapping mismatch")
        source_ip = target.get("source_ip")
        if not isinstance(source_ip, str):
            raise ValidationError(f"{target_node} has no current source_ip")
        source_ip = validate_service_source_ip(source_ip)

        runtime = Stage4BShadowRuntime(policy_path=args.policy)
        initial = runtime.refresh()
        if _active_by_code(initial, TARGET_ALERT):
            raise ValidationError(f"{TARGET_ALERT} already active before fault injection")
        if initial.get("safety", {}).get("control_policy_applied") is not False:
            raise ValidationError("shadow runtime unexpectedly applies control policy")

        fault_rule = HeartbeatDropRule.create(source_ip)
        rule_handle = fault_rule.install()
        fault_installed = True
        fault_started = time.monotonic()

        print(
            f"INFO: temporary heartbeat drop installed for {target_node} "
            f"source_ip={source_ip} handle={rule_handle}",
            flush=True,
        )

        offline_deadline = fault_started + args.offline_timeout
        offline_snapshot: dict[str, Any] | None = None
        while time.monotonic() < offline_deadline:
            _require_runtime_safety(
                core,
                expected_core_pid=core_pid,
                expected_agent_pid=agent_pid,
                baseline_counters=baseline_counters,
            )
            fault_rule.verify_installed()
            snapshot = runtime.refresh()
            target_public = _find_public_node(snapshot, target_node)
            other_public = _find_public_node(snapshot, other_node)
            if other_public.get("online") is not True:
                raise ValidationError(f"non-target {other_node} heartbeat went offline")
            if target_public.get("online") is False:
                matches = _active_by_code(snapshot, TARGET_ALERT)
                if len(matches) != 1:
                    raise ValidationError(
                        f"expected exactly one {TARGET_ALERT} after target offline, got {len(matches)}"
                    )
                alert_v2 = matches[0].get("alert_v2")
                if not isinstance(alert_v2, dict):
                    raise ValidationError(f"{TARGET_ALERT} missing AlertV2 policy metadata")
                if alert_v2.get("weight") != 2 or alert_v2.get("hmi_color") != "yellow":
                    raise ValidationError(
                        f"unexpected {TARGET_ALERT} policy: weight={alert_v2.get('weight')!r} "
                        f"color={alert_v2.get('hmi_color')!r}"
                    )
                if alert_v2.get("affects_control") is not False:
                    raise ValidationError(f"{TARGET_ALERT} unexpectedly affects control")
                if snapshot.get("correlation", {}).get("derived_codes") != [TARGET_ALERT]:
                    raise ValidationError(
                        f"unexpected correlation derived_codes: "
                        f"{snapshot.get('correlation', {}).get('derived_codes')!r}"
                    )
                offline_snapshot = snapshot
                offline_detected_after = time.monotonic() - fault_started
                break
            time.sleep(args.poll_interval)

        if offline_snapshot is None:
            raise ValidationError(
                f"{target_node} did not transition offline within {args.offline_timeout:.1f}s"
            )

        # Restore heartbeat immediately after the expected alert has been proven.
        fault_rule.remove()
        fault_installed = False
        recovery_started = time.monotonic()
        print(
            f"INFO: heartbeat drop removed after {offline_detected_after:.3f}s; waiting for recovery",
            flush=True,
        )

        recovery_deadline = recovery_started + args.recovery_timeout
        recovered_snapshot: dict[str, Any] | None = None
        while time.monotonic() < recovery_deadline:
            _require_runtime_safety(
                core,
                expected_core_pid=core_pid,
                expected_agent_pid=agent_pid,
                baseline_counters=baseline_counters,
            )
            service = read_service_agent_status(
                Path("/run/wvc-service-agent/service-agent.sock"), 0.35
            )
            _require_service_network_healthy(service)
            target_now = _node_by_id(service, target_node)
            other_now = _node_by_id(service, other_node)
            if other_now.get("online") is not True:
                raise ValidationError(f"non-target {other_node} went offline during recovery")
            snapshot = runtime.refresh()
            if target_now.get("online") is True and not _active_by_code(snapshot, TARGET_ALERT):
                recovered_snapshot = snapshot
                recovered_after = time.monotonic() - recovery_started
                break
            time.sleep(args.poll_interval)

        if recovered_snapshot is None:
            raise ValidationError(
                f"{target_node} heartbeat/alert did not recover within {args.recovery_timeout:.1f}s"
            )

        _require_runtime_safety(
            core,
            expected_core_pid=core_pid,
            expected_agent_pid=agent_pid,
            baseline_counters=baseline_counters,
        )
        if find_stage4c_handles(list_input_chain()):
            raise ValidationError("Stage 4C nft rule remains after recovery")

        result = {
            "result": "PASS",
            "stage": "AlertV2 Stage 4C heartbeat-only dropout",
            "target": {
                "node_id": target_node,
                "modbus_address": target_address,
                "source_ip": source_ip,
                "temporary_nft_handle": rule_handle,
            },
            "fault": {
                "heartbeat_only": True,
                "offline_detected_after_s": round(float(offline_detected_after), 3),
                "recovered_after_s": round(float(recovered_after), 3),
                "expected_alert": TARGET_ALERT,
                "weight": 2,
                "hmi_color": "yellow",
                "affects_control": False,
            },
            "production": {
                "core_pid": core_pid,
                "service_agent_pid": agent_pid,
                "mode": safety.mode,
                "setpoints_v": {
                    "supply": safety.supply_voltage,
                    "extract": safety.extract_voltage,
                },
                "sensor_bus_error_counters_unchanged": True,
            },
            "safety": {
                "control_policy_applied": False,
                "write_commands_sent": 0,
                "hardware_owned_by_shadow": False,
                "temporary_firewall_rule_removed": True,
            },
            "recovery": {
                "target_online": True,
                "alert_cleared": True,
                "non_target_online": True,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        print("PASS: heartbeat-only dropout produced KAMOD_HEARTBEAT_LOST")
        print("PASS: production SENSOR BUS remained healthy with unchanged error counters")
        print("PASS: AlertV2 weight=2 / yellow / affects_control=false")
        print("PASS: heartbeat recovered and KAMOD_HEARTBEAT_LOST cleared")
        print("PASS: production remained STOP / 0 V and no control command was sent")
        return 0
    except (ValidationError, Stage4CFaultError, OSError, KeyboardInterrupt) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if fault_installed and fault_rule is not None:
            try:
                fault_rule.remove()
                print("CLEANUP: temporary Stage 4C nft rule removed", file=sys.stderr)
            except Exception as cleanup_exc:
                print(
                    "CRITICAL CLEANUP FAILURE: temporary heartbeat drop may still be active: "
                    f"{cleanup_exc}",
                    file=sys.stderr,
                )
        if runtime is not None:
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
