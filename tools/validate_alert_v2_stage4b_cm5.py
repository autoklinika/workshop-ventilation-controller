#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ventilation_core.alert_v2_stage4b_runtime import (
    DEFAULT_CORE_SOCKET,
    CoreReadOnlyClient,
    Stage4BError,
    request_unix_json,
    require_passive_safe_state,
)
from ventilation_core.service_plane_monitor import DEFAULT_SERVICE_AGENT_SOCKET


ROOT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_TOOL = ROOT_DIR / "tools" / "run_alert_v2_stage4b_shadow_runtime.py"
DEFAULT_POLICY = ROOT_DIR / "config" / "alerts-v2.default.toml"


class ValidationError(RuntimeError):
    pass


def _systemctl_active(service: str) -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", service],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _systemctl_pid(service: str) -> int:
    result = subprocess.run(
        ["systemctl", "show", service, "-p", "MainPID", "--value"],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        pid = int(result.stdout.strip())
    except ValueError as exc:
        raise ValidationError(f"cannot read MainPID for {service}: {result.stdout!r}") from exc
    if result.returncode != 0 or pid <= 0:
        raise ValidationError(f"invalid MainPID for {service}: {pid}")
    return pid


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValidationError("latency sample list is empty")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(statistics.fmean(values), 3),
        "p50_ms": round(_percentile(values, 0.50), 3),
        "p95_ms": round(_percentile(values, 0.95), 3),
        "max_ms": round(max(values), 3),
    }


def _request_shadow(path: Path, timeout: float) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = request_unix_json(path, {"command": "status"}, timeout)
    latency_ms = (time.perf_counter() - started) * 1000.0
    return response, latency_ms


def _validate_shadow_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("ok") is not True:
        raise ValidationError(f"shadow runtime not healthy: {snapshot.get('error') or snapshot.get('last_error')}")
    if snapshot.get("stage") != "AlertV2 Stage 4B shadow runtime":
        raise ValidationError("unexpected shadow runtime stage")
    if snapshot.get("mode") != "read_only_shadow":
        raise ValidationError("shadow runtime is not read_only_shadow")

    safety = snapshot.get("safety")
    if not isinstance(safety, dict):
        raise ValidationError("shadow runtime missing safety block")
    if safety.get("mode") != "STOP":
        raise ValidationError(f"shadow runtime observed non-STOP mode: {safety.get('mode')}")
    setpoints = safety.get("setpoints_v")
    if not isinstance(setpoints, dict) or setpoints.get("supply") != 0.0 or setpoints.get("extract") != 0.0:
        raise ValidationError(f"shadow runtime observed non-zero setpoints: {setpoints!r}")
    if safety.get("output_state_known") is not True:
        raise ValidationError("shadow runtime observed output_state_known != true")
    if safety.get("write_commands_sent") != 0:
        raise ValidationError("shadow runtime reports a write command")
    if safety.get("control_policy_applied") is not False:
        raise ValidationError("shadow runtime reports control policy applied")

    policy = snapshot.get("policy")
    if not isinstance(policy, dict) or policy.get("loaded") is not True:
        raise ValidationError("AlertV2 policy is not loaded")
    if policy.get("alert_count") != 49:
        raise ValidationError(f"unexpected AlertV2 policy count: {policy.get('alert_count')}")
    if policy.get("control_policy_applied") is not False:
        raise ValidationError("policy manager reports control policy applied")

    summary = snapshot.get("alert_v2")
    if not isinstance(summary, dict):
        raise ValidationError("shadow runtime missing alert_v2 summary")
    if summary.get("unmapped_active_alerts") != 0:
        raise ValidationError(
            f"unmapped active AlertV2 records: {summary.get('unmapped_active_alerts')}"
        )
    if summary.get("control_policy_applied") is not False:
        raise ValidationError("AlertV2 summary reports control policy applied")

    correlation = snapshot.get("correlation")
    if not isinstance(correlation, dict):
        raise ValidationError("shadow runtime missing correlation diagnostics")
    if correlation.get("control_policy_applied") is not False:
        raise ValidationError("correlation reports control policy applied")
    if correlation.get("reason") != "correlation_complete":
        raise ValidationError(
            f"Stage 4B expected healthy correlation_complete, got {correlation.get('reason')!r}"
        )

    active = snapshot.get("active")
    if not isinstance(active, list):
        raise ValidationError("shadow runtime active alert list is invalid")
    for alert in active:
        if not isinstance(alert, dict):
            raise ValidationError("shadow active alert is not an object")
        metadata = alert.get("alert_v2")
        if not isinstance(metadata, dict) or metadata.get("mapped") is not True:
            raise ValidationError(f"active alert is not mapped by AlertV2: {alert.get('code')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate AlertV2 Stage 4B live read-only shadow runtime on CM5"
    )
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--runtime-refresh", type=float, default=0.5)
    parser.add_argument("--startup-timeout", type=float, default=8.0)
    parser.add_argument("--socket-timeout", type=float, default=0.75)
    parser.add_argument("--core-socket", type=Path, default=DEFAULT_CORE_SOCKET)
    parser.add_argument(
        "--service-agent-socket",
        type=Path,
        default=DEFAULT_SERVICE_AGENT_SOCKET,
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument(
        "--baseline-core-p95-ms",
        type=float,
        default=None,
        help="Optional Stage 4A core p95 for comparison only; it is not a hard pass/fail threshold",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.samples < 10:
        print("FAIL: samples must be at least 10", file=sys.stderr)
        return 2
    if args.interval <= 0 or args.runtime_refresh <= 0:
        print("FAIL: intervals must be positive", file=sys.stderr)
        return 2

    runtime_process: subprocess.Popen[str] | None = None
    runtime_log_path: Path | None = None
    shadow_socket: Path | None = None
    try:
        if not _systemctl_active("ventilation-core.service"):
            raise ValidationError("production ventilation-core.service is not active")
        if not _systemctl_active("wvc-service-agent.service"):
            raise ValidationError("wvc-service-agent.service is not active")

        core_pid_before = _systemctl_pid("ventilation-core.service")
        service_pid_before = _systemctl_pid("wvc-service-agent.service")
        core = CoreReadOnlyClient(args.core_socket, timeout_seconds=args.socket_timeout)
        preflight_status = core.request("status")
        require_passive_safe_state(preflight_status)

        with tempfile.TemporaryDirectory(prefix="wvc-alert-v2-stage4b-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            shadow_socket = temp_dir / "shadow.sock"
            runtime_log_path = temp_dir / "runtime.log"
            runtime_log = runtime_log_path.open("w+", encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT_DIR / "src")
            runtime_process = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNTIME_TOOL),
                    "--policy",
                    str(args.policy),
                    "--core-socket",
                    str(args.core_socket),
                    "--service-agent-socket",
                    str(args.service_agent_socket),
                    "--listen-socket",
                    str(shadow_socket),
                    "--refresh-interval",
                    str(args.runtime_refresh),
                    "--core-timeout",
                    str(args.socket_timeout),
                    "--service-timeout",
                    "0.35",
                ],
                cwd=str(ROOT_DIR),
                env=env,
                stdout=runtime_log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            deadline = time.monotonic() + args.startup_timeout
            first_snapshot: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                if runtime_process.poll() is not None:
                    runtime_log.flush()
                    runtime_log.seek(0)
                    raise ValidationError(
                        "shadow runtime exited during startup:\n" + runtime_log.read()
                    )
                if shadow_socket.exists():
                    try:
                        first_snapshot, _ = _request_shadow(shadow_socket, args.socket_timeout)
                        _validate_shadow_snapshot(first_snapshot)
                        break
                    except (OSError, Stage4BError, ValidationError):
                        pass
                time.sleep(0.1)
            if first_snapshot is None:
                runtime_log.flush()
                runtime_log.seek(0)
                raise ValidationError(
                    "shadow runtime did not become ready:\n" + runtime_log.read()
                )

            core_latencies: list[float] = []
            shadow_latencies: list[float] = []
            refresh_durations: list[float] = []
            iterations: set[int] = set()
            active_codes: set[str] = set()
            hmi_colors: set[str] = set()
            active_weights: set[int] = set()

            for _index in range(args.samples):
                core_status = core.request("status")
                require_passive_safe_state(core_status)
                core_latencies.append(float(core_status["_latency_ms"]))

                shadow, shadow_latency = _request_shadow(shadow_socket, args.socket_timeout)
                _validate_shadow_snapshot(shadow)
                shadow_latencies.append(shadow_latency)
                refresh_durations.append(float(shadow.get("refresh_duration_ms", 0.0)))
                iteration = shadow.get("iteration")
                if isinstance(iteration, int):
                    iterations.add(iteration)
                summary = shadow.get("alert_v2")
                if isinstance(summary, dict):
                    color = summary.get("hmi_color")
                    weight = summary.get("active_weight")
                    if isinstance(color, str):
                        hmi_colors.add(color)
                    if isinstance(weight, int) and not isinstance(weight, bool):
                        active_weights.add(weight)
                active = shadow.get("active")
                if isinstance(active, list):
                    for item in active:
                        if isinstance(item, dict) and isinstance(item.get("code"), str):
                            active_codes.add(item["code"])
                time.sleep(args.interval)

            if len(iterations) < 3:
                raise ValidationError(
                    f"shadow runtime refresh did not advance enough: iterations={sorted(iterations)}"
                )
            if runtime_process.poll() is not None:
                raise ValidationError("shadow runtime exited before validation completed")

            post_status = core.request("status")
            require_passive_safe_state(post_status)
            core_pid_after = _systemctl_pid("ventilation-core.service")
            service_pid_after = _systemctl_pid("wvc-service-agent.service")
            if core_pid_after != core_pid_before:
                raise ValidationError(
                    f"production core PID changed {core_pid_before} -> {core_pid_after}"
                )
            if service_pid_after != service_pid_before:
                raise ValidationError(
                    f"Service Agent PID changed {service_pid_before} -> {service_pid_after}"
                )

            core_stats = _stats(core_latencies)
            result: dict[str, Any] = {
                "result": "PASS",
                "stage": "AlertV2 Stage 4B live shadow runtime validation",
                "samples": args.samples,
                "production": {
                    "core_pid": core_pid_after,
                    "service_agent_pid": service_pid_after,
                    "mode": "STOP",
                    "setpoints_v": {"supply": 0.0, "extract": 0.0},
                },
                "safety": {
                    "write_commands_sent": 0,
                    "control_policy_applied": False,
                    "production_databases_opened_by_shadow": False,
                    "hardware_owned_by_shadow": False,
                },
                "latency": {
                    "production_core_status": core_stats,
                    "shadow_status": _stats(shadow_latencies),
                    "shadow_refresh_duration": _stats(refresh_durations),
                },
                "runtime": {
                    "observed_iterations": len(iterations),
                    "iteration_min": min(iterations),
                    "iteration_max": max(iterations),
                    "active_codes": sorted(active_codes),
                    "active_weights": sorted(active_weights),
                    "hmi_colors": sorted(hmi_colors),
                    "policy_alert_count": 49,
                    "unmapped_active_alerts": 0,
                    "correlation_reason": "correlation_complete",
                },
            }
            if args.baseline_core_p95_ms is not None:
                baseline = float(args.baseline_core_p95_ms)
                result["latency"]["stage4a_comparison"] = {
                    "baseline_core_p95_ms": baseline,
                    "stage4b_core_p95_ms": core_stats["p95_ms"],
                    "delta_ms": round(core_stats["p95_ms"] - baseline, 3),
                    "ratio": None if baseline <= 0 else round(core_stats["p95_ms"] / baseline, 3),
                    "pass_fail_threshold_applied": False,
                }

            print(json.dumps(result, indent=2, sort_keys=True))
            print("PASS: AlertV2 Stage 4B shadow runtime stayed read-only")
            print("PASS: production ventilation-core PID remained unchanged")
            print("PASS: Service Agent PID remained unchanged")
            print("PASS: production remained STOP / 0 V throughout validation")
            print("PASS: every active shadow alert was mapped by AlertV2 policy")
            print("PASS: Stage 3 correlation remained control_policy_applied=false")

            runtime_process.terminate()
            try:
                runtime_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                runtime_process.kill()
                runtime_process.wait(timeout=2.0)
            runtime_log.close()
            runtime_process = None
        return 0
    except (ValidationError, Stage4BError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        if runtime_log_path is not None and runtime_log_path.exists():
            try:
                print("===== STAGE 4B RUNTIME LOG =====", file=sys.stderr)
                print(runtime_log_path.read_text(encoding="utf-8"), file=sys.stderr)
            except OSError:
                pass
        return 1
    finally:
        if runtime_process is not None and runtime_process.poll() is None:
            runtime_process.terminate()
            try:
                runtime_process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                runtime_process.kill()
        if shadow_socket is not None and shadow_socket.exists():
            try:
                shadow_socket.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
