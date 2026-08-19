#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ventilation_core.alert_policy import load_alert_policy
from ventilation_core.alert_v2_stage4b_runtime import (
    CoreReadOnlyClient,
    Stage4BError,
    require_passive_safe_state,
)


DEFAULT_POLICY = Path("/etc/workshop-ventilation/alerts-v2.toml")
EXPECTED_ALERT_COUNT = 49


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AlertV2 Stage 5: validate the production core read-only AlertV2 rollout "
            "without issuing any control command"
        )
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--core-timeout", type=float, default=1.0)
    parser.add_argument(
        "--expected-worktree",
        type=Path,
        default=Path("/home/wentylacja/wvc-alert-v2-stage4"),
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
        raise ValidationError(f"required service is not active: {unit}")
    raw = _systemctl_value(unit, "MainPID")
    try:
        pid = int(raw)
    except ValueError as exc:
        raise ValidationError(f"invalid MainPID for {unit}: {raw!r}") from exc
    if pid < 1:
        raise ValidationError(f"invalid MainPID for {unit}: {pid}")
    return pid


def _process_cwd(pid: int) -> Path:
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except OSError as exc:
        raise ValidationError(f"cannot resolve production core cwd for pid {pid}: {exc}") from exc


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValidationError("cannot calculate percentile from empty sample")
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(statistics.fmean(values), 3),
        "p50_ms": round(_percentile(values, 0.50), 3),
        "p95_ms": round(_percentile(values, 0.95), 3),
        "max_ms": round(max(values), 3),
    }


def _require_alert_v2_state(
    state: dict[str, Any],
    *,
    policy_version: str,
    policy_sha256: str,
    alert_count: int,
) -> dict[str, Any]:
    alert_v2 = state.get("alert_v2")
    if not isinstance(alert_v2, dict):
        raise ValidationError("production core state does not expose alert_v2")

    expected = {
        "runtime_mode": "read_only_mapping",
        "loaded": True,
        "policy_version": policy_version,
        "sha256": policy_sha256,
        "alert_count": alert_count,
        "control_policy_applied": False,
        "unmapped_active_alerts": 0,
    }
    actual = {field: alert_v2.get(field) for field in expected}
    if actual != expected:
        raise ValidationError(
            f"unexpected production alert_v2 state: {actual!r}, expected {expected!r}"
        )

    color = alert_v2.get("hmi_color")
    weight = alert_v2.get("active_weight")
    if weight not in {0, 1, 2, 3, 4}:
        raise ValidationError(f"invalid AlertV2 active_weight: {weight!r}")
    expected_color = {
        0: "green",
        1: "blue",
        2: "yellow",
        3: "orange",
        4: "red",
    }[weight]
    if color != expected_color:
        raise ValidationError(
            f"AlertV2 HMI color mismatch for weight {weight}: {color!r}"
        )

    service_plane = alert_v2.get("service_plane")
    if not isinstance(service_plane, dict):
        raise ValidationError("production AlertV2 service-plane diagnostics are unavailable")
    if service_plane.get("control_policy_applied") is not False:
        raise ValidationError("service-plane correlation reports control policy applied")

    monitor = service_plane.get("monitor")
    if not isinstance(monitor, dict) or monitor.get("available") is not True:
        raise ValidationError("Service Agent monitor is not available in production AlertV2")

    correlation = service_plane.get("correlation")
    if not isinstance(correlation, dict) or correlation.get("mode") != "read_only":
        raise ValidationError("production service-plane correlation is not read-only")

    return alert_v2


def _require_mapped_active_alerts(document: dict[str, Any]) -> int:
    active = document.get("active")
    if not isinstance(active, list):
        raise ValidationError("production alerts response missing active list")
    mapped = 0
    for record in active:
        if not isinstance(record, dict):
            continue
        metadata = record.get("alert_v2")
        if not isinstance(metadata, dict) or metadata.get("mapped") is not True:
            raise ValidationError(
                f"production active alert is not mapped by AlertV2: {record.get('code')!r}"
            )
        mapped += 1
    return mapped


def main() -> int:
    args = build_parser().parse_args()
    if args.samples < 5 or args.samples > 240:
        print("FAIL: --samples must be in range 5..240", file=sys.stderr)
        return 2
    if args.interval <= 0 or args.core_timeout <= 0:
        print("FAIL: timing arguments must be positive", file=sys.stderr)
        return 2

    try:
        policy = load_alert_policy(args.policy)
        if policy.alert_count != EXPECTED_ALERT_COUNT:
            raise ValidationError(
                f"Stage 5 expects {EXPECTED_ALERT_COUNT} policy entries, got {policy.alert_count}"
            )

        core_pid = _require_active_pid("ventilation-core.service")
        agent_pid = _require_active_pid("wvc-service-agent.service")
        core_cwd = _process_cwd(core_pid)
        expected_cwd = args.expected_worktree.resolve(strict=True)
        if core_cwd != expected_cwd:
            raise ValidationError(
                f"production core is not running from Stage 5 worktree: {core_cwd} != {expected_cwd}"
            )

        client = CoreReadOnlyClient(timeout_seconds=args.core_timeout)
        status_latencies: list[float] = []
        alerts_latencies: list[float] = []
        observed_weights: set[int] = set()
        observed_colors: set[str] = set()
        mapped_active_max = 0

        for _ in range(args.samples):
            if _require_active_pid("ventilation-core.service") != core_pid:
                raise ValidationError("production ventilation-core PID changed during Stage 5 validation")
            if _require_active_pid("wvc-service-agent.service") != agent_pid:
                raise ValidationError("Service Agent PID changed during Stage 5 validation")

            status = client.request("status")
            safety = require_passive_safe_state(status)
            state = status.get("state")
            if not isinstance(state, dict):
                raise ValidationError("production status missing state")
            if state.get("hardware_ready") is not True:
                raise ValidationError("production hardware_ready is not true")

            alert_v2 = _require_alert_v2_state(
                state,
                policy_version=policy.policy_version,
                policy_sha256=policy.sha256,
                alert_count=policy.alert_count,
            )
            weight = alert_v2.get("active_weight")
            color = alert_v2.get("hmi_color")
            if isinstance(weight, int) and not isinstance(weight, bool):
                observed_weights.add(weight)
            if isinstance(color, str):
                observed_colors.add(color)

            alerts = client.request("alerts", limit=200)
            mapped_active_max = max(mapped_active_max, _require_mapped_active_alerts(alerts))

            status_latencies.append(float(status["_latency_ms"]))
            alerts_latencies.append(float(alerts["_latency_ms"]))
            time.sleep(args.interval)

        final_status = client.request("status")
        final_safety = require_passive_safe_state(final_status)
        if _require_active_pid("ventilation-core.service") != core_pid:
            raise ValidationError("production core PID changed at end of Stage 5 validation")
        if _require_active_pid("wvc-service-agent.service") != agent_pid:
            raise ValidationError("Service Agent PID changed at end of Stage 5 validation")

        result = {
            "result": "PASS",
            "stage": "AlertV2 Stage 5 production read-only rollout validation",
            "production": {
                "core_pid": core_pid,
                "service_agent_pid": agent_pid,
                "core_cwd": str(core_cwd),
                "mode": final_safety.mode,
                "setpoints_v": {
                    "supply": final_safety.supply_voltage,
                    "extract": final_safety.extract_voltage,
                },
                "output_state_known": final_safety.output_state_known,
            },
            "policy": {
                "path": str(args.policy),
                "policy_version": policy.policy_version,
                "sha256": policy.sha256,
                "alert_count": policy.alert_count,
            },
            "runtime": {
                "mode": "read_only_mapping",
                "control_policy_applied": False,
                "service_plane_correlation": "read_only",
                "mapped_active_alerts_max": mapped_active_max,
                "observed_active_weights": sorted(observed_weights),
                "observed_hmi_colors": sorted(observed_colors),
            },
            "latency": {
                "core_status": _latency_summary(status_latencies),
                "core_alerts": _latency_summary(alerts_latencies),
            },
            "safety": {
                "control_commands_sent_by_validator": 0,
                "reaction_execution_enabled": False,
                "production_alert_store_is_authoritative": True,
            },
            "samples": args.samples,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        print("PASS: production core publishes AlertV2 read-only mapping")
        print("PASS: policy version/SHA/count match /etc runtime policy")
        print("PASS: Service Plane correlation is live and control_policy_applied=false")
        print("PASS: every active production alert is mapped by AlertV2")
        print("PASS: production remained STOP / 0 V throughout validation")
        print("PASS: validator sent zero control commands")
        return 0
    except (ValidationError, Stage4BError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
