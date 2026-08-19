#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ventilation_core.alert_v2_stage4b_runtime import (
    CoreReadOnlyClient,
    Stage4BError,
    Stage4BShadowRuntime,
    require_passive_safe_state,
)
from ventilation_core.service_plane_monitor import read_service_agent_status


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "config" / "alerts-v2.default.toml"
SERVICE_AGENT_SOCKET = Path("/run/wvc-service-agent/service-agent.sock")
EXPECTED_NODE_MAPPING = {
    "sensor-node-1": 1,
    "sensor-node-2": 2,
}
PRODUCTION_ALERT = "SENSOR_NODE_UNAVAILABLE"
CORRELATED_ALERT = "KAMOD_NODE_UNAVAILABLE"
TRANSITIONAL_HEARTBEAT_ALERT = "KAMOD_HEARTBEAT_LOST"


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AlertV2 Stage 4D: manual power-loss validation of one KAmod/SEN55 node "
            "with read-only correlation"
        )
    )
    parser.add_argument(
        "--target-node",
        choices=tuple(EXPECTED_NODE_MAPPING),
        default="sensor-node-1",
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--modbus-timeout", type=float, default=20.0)
    parser.add_argument("--correlation-timeout", type=float, default=60.0)
    parser.add_argument("--recovery-timeout", type=float, default=90.0)
    parser.add_argument(
        "--confirm-manual-power-cycle",
        action="store_true",
        help=(
            "Required acknowledgement that the operator will manually power-cycle ONLY "
            "the selected sensor node and that it can be isolated without interrupting "
            "the other node or CM5"
        ),
    )
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def _read_service_status() -> dict[str, Any]:
    return read_service_agent_status(SERVICE_AGENT_SOCKET, 0.35)


def _require_service_network_healthy(service: dict[str, Any]) -> None:
    network = service.get("network")
    if not isinstance(network, dict):
        raise ValidationError("Service Agent status missing network")
    required = (
        "ready",
        "ap_active",
        "address_present",
        "dhcp_active",
        "firewall_active",
    )
    failed = [field for field in required if network.get(field) is not True]
    if failed:
        raise ValidationError(f"WVC-SERVICE is not healthy: {failed}")


def _service_node(service: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = service.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError("Service Agent status missing nodes list")
    matches = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("node_id") == node_id
    ]
    if len(matches) != 1:
        raise ValidationError(
            f"Service Agent expected exactly one {node_id}, got {len(matches)}"
        )
    return matches[0]


def _sensor_nodes(status: dict[str, Any]) -> dict[int, dict[str, Any]]:
    state = status.get("state")
    sensor_bus = state.get("sensor_bus") if isinstance(state, dict) else None
    if not isinstance(sensor_bus, dict):
        raise ValidationError("production core status missing SENSOR BUS")
    if sensor_bus.get("worker_alive") is not True or sensor_bus.get("ready") is not True:
        raise ValidationError("production SENSOR BUS worker is not ready/alive")
    raw_nodes = sensor_bus.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValidationError("production SENSOR BUS missing nodes list")
    nodes: dict[int, dict[str, Any]] = {}
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        address = node.get("slave_address")
        if isinstance(address, int) and not isinstance(address, bool):
            nodes[address] = node
    for address in EXPECTED_NODE_MAPPING.values():
        if address not in nodes:
            raise ValidationError(f"production SENSOR BUS missing slave {address}")
    return nodes


def _require_sensor_healthy(node: dict[str, Any], label: str) -> None:
    if node.get("online") is not True or node.get("usable") is not True:
        raise ValidationError(f"{label} is not online+usable")
    if node.get("measurement_valid") is not True or node.get("measurement_stale") is not False:
        raise ValidationError(f"{label} measurement is not healthy")
    if node.get("consecutive_failures") != 0:
        raise ValidationError(f"{label} has consecutive failures")


def _counter_snapshot(node: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for field in (
        "communication_errors",
        "invalid_measurements",
        "stale_measurements",
        "map_version_errors",
    ):
        value = node.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError(f"invalid SENSOR BUS counter {field}={value!r}")
        result[field] = value
    return result


def _require_non_target_healthy(
    status: dict[str, Any],
    service: dict[str, Any],
    *,
    node_id: str,
    address: int,
    baseline_counters: dict[str, int],
) -> None:
    nodes = _sensor_nodes(status)
    node = nodes[address]
    _require_sensor_healthy(node, f"non-target SENSOR BUS slave {address}")
    current_counters = _counter_snapshot(node)
    if current_counters != baseline_counters:
        raise ValidationError(
            f"non-target slave {address} counters changed: "
            f"{baseline_counters} -> {current_counters}"
        )
    service_node = _service_node(service, node_id)
    if service_node.get("online") is not True:
        raise ValidationError(f"non-target {node_id} heartbeat went offline")
    if service_node.get("modbus_address") != address:
        raise ValidationError(f"non-target {node_id} mapping changed")


def _require_runtime_safety(
    core: CoreReadOnlyClient,
    *,
    expected_core_pid: int,
    expected_agent_pid: int,
) -> dict[str, Any]:
    if _require_active_pid("ventilation-core.service") != expected_core_pid:
        raise ValidationError("production ventilation-core PID changed during Stage 4D")
    if _require_active_pid("wvc-service-agent.service") != expected_agent_pid:
        raise ValidationError("production Service Agent PID changed during Stage 4D")
    status = core.request("status")
    require_passive_safe_state(status)
    return status


def _active_alerts(core: CoreReadOnlyClient) -> list[dict[str, Any]]:
    document = core.request("alerts", limit=200)
    active = document.get("active")
    if not isinstance(active, list):
        raise ValidationError("production core alerts response missing active list")
    return [item for item in active if isinstance(item, dict)]


def _history_alerts(core: CoreReadOnlyClient) -> list[dict[str, Any]]:
    document = core.request("alerts", limit=200)
    history = document.get("history")
    if not isinstance(history, list):
        raise ValidationError("production core alerts response missing history list")
    return [item for item in history if isinstance(item, dict)]


def _matching_alerts(
    alerts: list[dict[str, Any]],
    *,
    code: str,
    key: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in alerts:
        if item.get("code") != code:
            continue
        if key is not None and item.get("key") != key:
            continue
        if source is not None and item.get("source") != source:
            continue
        result.append(item)
    return result


def _shadow_alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    active = snapshot.get("active")
    if not isinstance(active, list):
        raise ValidationError("shadow runtime missing active alert list")
    return [item for item in active if isinstance(item, dict)]


def _public_service_node(snapshot: dict[str, Any], node_id: str) -> dict[str, Any]:
    service_plane = snapshot.get("service_plane")
    nodes = service_plane.get("nodes") if isinstance(service_plane, dict) else None
    if not isinstance(nodes, list):
        raise ValidationError("shadow runtime missing service-plane node diagnostics")
    matches = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("node_id") == node_id
    ]
    if len(matches) != 1:
        raise ValidationError(f"shadow runtime expected exactly one {node_id}")
    return matches[0]


def _validate_correlated_alert(
    snapshot: dict[str, Any],
    *,
    correlated_key: str,
    production_key: str,
) -> dict[str, Any]:
    active = _shadow_alerts(snapshot)
    matches = _matching_alerts(active, code=CORRELATED_ALERT, key=correlated_key)
    if len(matches) != 1:
        raise ValidationError(
            f"expected exactly one {CORRELATED_ALERT}/{correlated_key}, got {len(matches)}"
        )
    if _matching_alerts(active, code=PRODUCTION_ALERT, key=production_key):
        raise ValidationError(
            f"legacy {PRODUCTION_ALERT}/{production_key} was not suppressed in shadow projection"
        )
    alert_v2 = matches[0].get("alert_v2")
    if not isinstance(alert_v2, dict) or alert_v2.get("mapped") is not True:
        raise ValidationError(f"{CORRELATED_ALERT} is not mapped by AlertV2 policy")
    expected = {
        "weight": 3,
        "hmi_color": "orange",
        "reaction": "fallback_local",
        "affects_control": True,
    }
    actual = {field: alert_v2.get(field) for field in expected}
    if actual != expected:
        raise ValidationError(
            f"unexpected {CORRELATED_ALERT} policy metadata: {actual!r}, expected {expected!r}"
        )

    correlation = snapshot.get("correlation")
    if not isinstance(correlation, dict):
        raise ValidationError("shadow runtime missing correlation diagnostics")
    derived_codes = correlation.get("derived_codes")
    suppressed = correlation.get("suppressed_legacy_keys")
    if derived_codes != [CORRELATED_ALERT]:
        raise ValidationError(f"unexpected derived_codes: {derived_codes!r}")
    if not isinstance(suppressed, list) or production_key not in suppressed:
        raise ValidationError(
            f"production key {production_key} not reported as suppressed: {suppressed!r}"
        )
    if correlation.get("control_policy_applied") is not False:
        raise ValidationError("correlation unexpectedly reports control policy applied")
    safety = snapshot.get("safety")
    if not isinstance(safety, dict) or safety.get("control_policy_applied") is not False:
        raise ValidationError("shadow runtime unexpectedly applies control policy")
    if safety.get("write_commands_sent") != 0:
        raise ValidationError("shadow runtime unexpectedly reports a write command")
    return matches[0]


def _install_signal_guards() -> None:
    def handler(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main() -> int:
    args = build_parser().parse_args()
    if not args.confirm_manual_power_cycle:
        print(
            "FAIL: Stage 4D requires --confirm-manual-power-cycle. "
            "Run only if the selected KAmod/SEN55 can be powered off independently "
            "without interrupting CM5 or the other sensor node.",
            file=sys.stderr,
        )
        return 2
    if (
        args.poll_interval <= 0
        or args.modbus_timeout < 5
        or args.correlation_timeout < 40
        or args.recovery_timeout < 30
    ):
        print("FAIL: invalid Stage 4D timing arguments", file=sys.stderr)
        return 2

    _install_signal_guards()
    target_node_id = args.target_node
    target_address = EXPECTED_NODE_MAPPING[target_node_id]
    other_node_id = next(node for node in EXPECTED_NODE_MAPPING if node != target_node_id)
    other_address = EXPECTED_NODE_MAPPING[other_node_id]
    production_key = f"sensor-node:{target_address}:communication"
    correlated_key = f"sensor-node:{target_address}:correlated-unavailable"

    runtime: Stage4BShadowRuntime | None = None
    physical_fault_armed = False
    recovery_confirmed = False
    production_alert_id: int | None = None
    power_off_confirmed_at: float | None = None
    modbus_failed_after: float | None = None
    correlated_after: float | None = None
    recovery_after: float | None = None

    try:
        core_pid = _require_active_pid("ventilation-core.service")
        agent_pid = _require_active_pid("wvc-service-agent.service")
        core = CoreReadOnlyClient()

        baseline_status = _require_runtime_safety(
            core,
            expected_core_pid=core_pid,
            expected_agent_pid=agent_pid,
        )
        baseline_nodes = _sensor_nodes(baseline_status)
        _require_sensor_healthy(
            baseline_nodes[target_address],
            f"target SENSOR BUS slave {target_address}",
        )
        _require_sensor_healthy(
            baseline_nodes[other_address],
            f"non-target SENSOR BUS slave {other_address}",
        )
        other_baseline_counters = _counter_snapshot(baseline_nodes[other_address])

        service = _read_service_status()
        _require_service_network_healthy(service)
        target_service = _service_node(service, target_node_id)
        other_service = _service_node(service, other_node_id)
        if target_service.get("online") is not True or other_service.get("online") is not True:
            raise ValidationError("both KAmod heartbeats must be online before Stage 4D")
        if target_service.get("modbus_address") != target_address:
            raise ValidationError(
                f"{target_node_id} mapping mismatch: expected Modbus {target_address}, "
                f"got {target_service.get('modbus_address')!r}"
            )
        if other_service.get("modbus_address") != other_address:
            raise ValidationError(f"{other_node_id} mapping mismatch")

        if _matching_alerts(
            _active_alerts(core),
            code=PRODUCTION_ALERT,
            key=production_key,
        ):
            raise ValidationError(
                f"target production alert {PRODUCTION_ALERT}/{production_key} is already active"
            )

        runtime = Stage4BShadowRuntime(policy_path=args.policy)
        initial_shadow = runtime.refresh()
        if _matching_alerts(
            _shadow_alerts(initial_shadow),
            code=CORRELATED_ALERT,
            key=correlated_key,
        ):
            raise ValidationError(f"{CORRELATED_ALERT} is already active before Stage 4D")
        if initial_shadow.get("safety", {}).get("control_policy_applied") is not False:
            raise ValidationError("shadow runtime unexpectedly applies control policy")

        print()
        print("===== STAGE 4D MANUAL ACTION 1/2 =====", flush=True)
        print(
            f"POWER OFF ONLY {target_node_id} (Modbus slave {target_address}).",
            flush=True,
        )
        print(
            f"DO NOT power off CM5, {other_node_id}, SENSOR BUS converter or shared RS-485 infrastructure.",
            flush=True,
        )
        print(
            "If the target cannot be powered independently, press Ctrl+C and do not perform this test.",
            flush=True,
        )
        input("When ONLY the target node is physically powered OFF, press Enter to continue: ")
        physical_fault_armed = True
        power_off_confirmed_at = time.monotonic()

        modbus_deadline = power_off_confirmed_at + args.modbus_timeout
        while time.monotonic() < modbus_deadline:
            status = _require_runtime_safety(
                core,
                expected_core_pid=core_pid,
                expected_agent_pid=agent_pid,
            )
            service = _read_service_status()
            _require_service_network_healthy(service)
            _require_non_target_healthy(
                status,
                service,
                node_id=other_node_id,
                address=other_address,
                baseline_counters=other_baseline_counters,
            )
            target_sensor = _sensor_nodes(status)[target_address]
            active = _active_alerts(core)
            production_matches = _matching_alerts(
                active,
                code=PRODUCTION_ALERT,
                key=production_key,
                source=f"sensor:{target_address}",
            )
            if production_matches:
                if len(production_matches) != 1:
                    raise ValidationError(
                        f"expected one production {PRODUCTION_ALERT}, got {len(production_matches)}"
                    )
                if target_sensor.get("consecutive_failures", 0) < 3:
                    raise ValidationError(
                        f"production alert appeared before validated debounce: "
                        f"consecutive_failures={target_sensor.get('consecutive_failures')!r}"
                    )
                production_alert_id_raw = production_matches[0].get("alert_id")
                if isinstance(production_alert_id_raw, int) and not isinstance(
                    production_alert_id_raw, bool
                ):
                    production_alert_id = production_alert_id_raw
                modbus_failed_after = time.monotonic() - power_off_confirmed_at
                break
            time.sleep(args.poll_interval)
        if modbus_failed_after is None:
            raise ValidationError(
                f"production {PRODUCTION_ALERT} was not detected within "
                f"{args.modbus_timeout:.1f}s"
            )

        correlation_deadline = power_off_confirmed_at + args.correlation_timeout
        correlated_snapshot: dict[str, Any] | None = None
        while time.monotonic() < correlation_deadline:
            status = _require_runtime_safety(
                core,
                expected_core_pid=core_pid,
                expected_agent_pid=agent_pid,
            )
            service = _read_service_status()
            _require_service_network_healthy(service)
            _require_non_target_healthy(
                status,
                service,
                node_id=other_node_id,
                address=other_address,
                baseline_counters=other_baseline_counters,
            )
            if not _matching_alerts(
                _active_alerts(core),
                code=PRODUCTION_ALERT,
                key=production_key,
            ):
                raise ValidationError(
                    f"production {PRODUCTION_ALERT} cleared before correlation completed"
                )

            snapshot = runtime.refresh()
            public_target = _public_service_node(snapshot, target_node_id)
            public_other = _public_service_node(snapshot, other_node_id)
            if public_other.get("online") is not True:
                raise ValidationError(f"non-target {other_node_id} heartbeat went offline")
            if public_target.get("online") is False:
                _validate_correlated_alert(
                    snapshot,
                    correlated_key=correlated_key,
                    production_key=production_key,
                )
                correlated_snapshot = snapshot
                correlated_after = time.monotonic() - power_off_confirmed_at
                break
            time.sleep(args.poll_interval)

        if correlated_snapshot is None:
            raise ValidationError(
                f"{CORRELATED_ALERT} was not confirmed within "
                f"{args.correlation_timeout:.1f}s from manual power-off"
            )

        print()
        print("===== STAGE 4D MANUAL ACTION 2/2 =====", flush=True)
        print(f"RESTORE POWER to {target_node_id} now.", flush=True)
        input("When target power is restored, press Enter to begin recovery validation: ")
        recovery_started = time.monotonic()

        recovery_deadline = recovery_started + args.recovery_timeout
        while time.monotonic() < recovery_deadline:
            status = _require_runtime_safety(
                core,
                expected_core_pid=core_pid,
                expected_agent_pid=agent_pid,
            )
            service = _read_service_status()
            _require_service_network_healthy(service)
            _require_non_target_healthy(
                status,
                service,
                node_id=other_node_id,
                address=other_address,
                baseline_counters=other_baseline_counters,
            )

            target_sensor = _sensor_nodes(status)[target_address]
            target_service = _service_node(service, target_node_id)
            shadow = runtime.refresh()
            shadow_active = _shadow_alerts(shadow)
            production_active = _active_alerts(core)

            target_sensor_healthy = (
                target_sensor.get("online") is True
                and target_sensor.get("usable") is True
                and target_sensor.get("measurement_valid") is True
                and target_sensor.get("measurement_stale") is False
                and target_sensor.get("consecutive_failures") == 0
            )
            target_heartbeat_healthy = target_service.get("online") is True
            production_alert_cleared = not _matching_alerts(
                production_active,
                code=PRODUCTION_ALERT,
                key=production_key,
            )
            correlated_cleared = not _matching_alerts(
                shadow_active,
                code=CORRELATED_ALERT,
                key=correlated_key,
            )
            transitional_heartbeat_cleared = not _matching_alerts(
                shadow_active,
                code=TRANSITIONAL_HEARTBEAT_ALERT,
                source=f"sensor:{target_address}",
            )

            if (
                target_sensor_healthy
                and target_heartbeat_healthy
                and production_alert_cleared
                and correlated_cleared
                and transitional_heartbeat_cleared
            ):
                recovery_confirmed = True
                recovery_after = time.monotonic() - recovery_started
                break
            time.sleep(args.poll_interval)

        if not recovery_confirmed:
            raise ValidationError(
                f"target node did not fully recover within {args.recovery_timeout:.1f}s"
            )

        final_status = _require_runtime_safety(
            core,
            expected_core_pid=core_pid,
            expected_agent_pid=agent_pid,
        )
        final_service = _read_service_status()
        _require_service_network_healthy(final_service)
        _require_non_target_healthy(
            final_status,
            final_service,
            node_id=other_node_id,
            address=other_address,
            baseline_counters=other_baseline_counters,
        )
        _require_sensor_healthy(
            _sensor_nodes(final_status)[target_address],
            f"recovered target SENSOR BUS slave {target_address}",
        )
        if _service_node(final_service, target_node_id).get("online") is not True:
            raise ValidationError("target heartbeat is not online after recovery")

        cleared_history = _matching_alerts(
            _history_alerts(core),
            code=PRODUCTION_ALERT,
            key=production_key,
            source=f"sensor:{target_address}",
        )
        if production_alert_id is not None:
            cleared_history = [
                item for item in cleared_history if item.get("alert_id") == production_alert_id
            ]
        if not cleared_history:
            raise ValidationError(
                "cleared production SENSOR_NODE_UNAVAILABLE incident is missing from alert history"
            )
        if not any(
            item.get("active") is False and isinstance(item.get("cleared_at"), str)
            for item in cleared_history
        ):
            raise ValidationError(
                "production SENSOR_NODE_UNAVAILABLE history record is not marked CLEARED"
            )

        final_shadow = runtime.refresh()
        if _matching_alerts(
            _shadow_alerts(final_shadow),
            code=CORRELATED_ALERT,
            key=correlated_key,
        ):
            raise ValidationError(f"{CORRELATED_ALERT} remains active after recovery")
        if final_shadow.get("safety", {}).get("control_policy_applied") is not False:
            raise ValidationError("shadow runtime unexpectedly applies control policy")
        if runtime.write_commands_sent != 0:
            raise ValidationError("shadow runtime reports a write command")

        result = {
            "result": "PASS",
            "stage": "AlertV2 Stage 4D correlated node power loss",
            "target": {
                "node_id": target_node_id,
                "modbus_address": target_address,
            },
            "fault": {
                "physical_power_cycle": True,
                "software_fault_injection": False,
                "production_sensor_alert": PRODUCTION_ALERT,
                "production_alert_key": production_key,
                "production_alert_id": production_alert_id,
                "production_alert_detected_after_s": round(float(modbus_failed_after), 3),
                "correlated_alert": CORRELATED_ALERT,
                "correlated_key": correlated_key,
                "correlated_after_s": round(float(correlated_after), 3),
                "weight": 3,
                "hmi_color": "orange",
                "reaction": "fallback_local",
                "affects_control": True,
            },
            "recovery": {
                "target_sensor_bus_healthy": True,
                "target_heartbeat_online": True,
                "correlated_alert_cleared": True,
                "production_alert_cleared": True,
                "production_test_incident_retained_in_history": True,
                "recovered_after_power_restore_s": round(float(recovery_after), 3),
            },
            "production": {
                "core_pid": core_pid,
                "service_agent_pid": agent_pid,
                "mode": "STOP",
                "setpoints_v": {"supply": 0.0, "extract": 0.0},
                "non_target_node_healthy": True,
            },
            "safety": {
                "control_policy_applied": False,
                "write_commands_sent": 0,
                "hardware_owned_by_shadow": False,
                "software_fault_injection": False,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        print(f"PASS: production {PRODUCTION_ALERT} detected for the powered-off target")
        print(f"PASS: heartbeat + SENSOR BUS failure correlated to {CORRELATED_ALERT}")
        print("PASS: AlertV2 weight=3 / orange / fallback_local mapping is read-only")
        print("PASS: non-target node remained healthy")
        print("PASS: target Modbus and heartbeat recovered and correlated alert cleared")
        print("PASS: production test incident is CLEARED and intentionally retained in alert history")
        print("PASS: production remained STOP / 0 V and shadow sent zero control commands")
        return 0

    except KeyboardInterrupt as exc:
        print(f"FAIL: Stage 4D interrupted: {exc}", file=sys.stderr)
        return 130
    except (ValidationError, Stage4BError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if runtime is not None:
            runtime.close()
        if physical_fault_armed and not recovery_confirmed:
            print(
                "\nACTION REQUIRED FOR RECOVERY: Stage 4D cannot restore physical power. "
                f"Ensure power is restored to {target_node_id} NOW, then verify both SENSOR BUS "
                "nodes, both service heartbeats, ventilation-core.service and STOP / 0 V state.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    raise SystemExit(main())
