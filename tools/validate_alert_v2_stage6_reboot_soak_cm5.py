#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ventilation_core.alert_policy import load_alert_policy
from ventilation_core.alert_v2_stage4b_runtime import (
    CoreReadOnlyClient,
    Stage4BError,
    require_passive_safe_state,
)


DEFAULT_POLICY = Path("/etc/workshop-ventilation/alerts-v2.toml")
DEFAULT_BASELINE = Path("/var/lib/workshop-ventilation/alert-v2-stage6-reboot-baseline.json")
DEFAULT_EXPECTED_RUNTIME = Path("/home/wentylacja/wvc-alert-v2-stage4")
DEFAULT_WEB_BASE_URL = "http://127.0.0.1:18091"
EXPECTED_ALERT_COUNT = 49
MAX_PERSISTENCE_IDS = 50
WEB_GET_PATHS = ("/api/v1/state", "/api/v1/alerts", "/api/v1/health")


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AlertV2 Stage 6: persist a pre-reboot baseline and validate reboot/soak "
            "stability without issuing ventilation control commands"
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
        command.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
        command.add_argument("--expected-runtime", type=Path, default=DEFAULT_EXPECTED_RUNTIME)
        command.add_argument("--core-timeout", type=float, default=1.0)
        command.add_argument("--web-timeout", type=float, default=1.5)
        command.add_argument("--web-base-url", default=DEFAULT_WEB_BASE_URL)

    prepare = sub.add_parser("prepare", help="record the validated pre-reboot baseline")
    common(prepare)

    verify = sub.add_parser("verify", help="validate reboot persistence and run the read-only soak")
    common(verify)
    verify.add_argument("--duration", type=float, default=180.0)
    verify.add_argument("--interval", type=float, default=1.0)
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
        raise ValidationError(f"systemctl show failed for {unit}: {completed.stderr.strip()}")
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


def _boot_id() -> str:
    value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    if not value:
        raise ValidationError("kernel boot_id is empty")
    return value


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


def _http_get_json(base_url: str, path: str, timeout_seconds: float) -> tuple[dict[str, Any], float]:
    if path not in WEB_GET_PATHS:
        raise ValidationError(f"Stage 6 forbids web path: {path}")
    started = time.perf_counter()
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if response.status != 200:
                raise ValidationError(f"web {path} returned HTTP {response.status}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValidationError(f"web GET {path} failed: {exc}") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if len(raw) > 2 * 1024 * 1024:
        raise ValidationError(f"web {path} response exceeds 2 MiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"web {path} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"web {path} response is not an object")
    return payload, elapsed_ms


def _require_alert_v2_state(
    state: dict[str, Any],
    *,
    policy_version: str,
    policy_sha256: str,
    alert_count: int,
) -> dict[str, Any]:
    alert_v2 = state.get("alert_v2")
    if not isinstance(alert_v2, dict):
        raise ValidationError("production state does not expose alert_v2")
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
        raise ValidationError(f"unexpected AlertV2 runtime state: {actual!r}")
    weight = alert_v2.get("active_weight")
    color = alert_v2.get("hmi_color")
    expected_color = {0: "green", 1: "blue", 2: "yellow", 3: "orange", 4: "red"}
    if weight not in expected_color or color != expected_color[weight]:
        raise ValidationError(f"invalid AlertV2 HMI weight/color pair: {weight!r}/{color!r}")
    service_plane = alert_v2.get("service_plane")
    if not isinstance(service_plane, dict):
        raise ValidationError("AlertV2 service_plane diagnostics missing")
    if service_plane.get("control_policy_applied") is not False:
        raise ValidationError("Service Plane reports control policy applied")
    correlation = service_plane.get("correlation")
    if not isinstance(correlation, dict) or correlation.get("mode") != "read_only":
        raise ValidationError("Service Plane correlation is not read-only")
    monitor = service_plane.get("monitor")
    if not isinstance(monitor, dict) or monitor.get("available") is not True:
        raise ValidationError("Service Agent monitor is not available")
    return alert_v2


def _require_mapped_active_alerts(document: dict[str, Any]) -> int:
    active = document.get("active")
    history = document.get("history")
    if not isinstance(active, list) or not isinstance(history, list):
        raise ValidationError("alerts response missing active/history lists")
    mapped = 0
    for record in active:
        if not isinstance(record, dict):
            continue
        metadata = record.get("alert_v2")
        if not isinstance(metadata, dict) or metadata.get("mapped") is not True:
            raise ValidationError(f"active alert is not mapped: {record.get('code')!r}")
        mapped += 1
    return mapped


def _incident_ids(document: dict[str, Any]) -> list[int]:
    values: set[int] = set()
    for section in ("active", "history"):
        records = document.get(section)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            raw = record.get("id", record.get("alert_id"))
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
                values.add(raw)
    return sorted(values, reverse=True)[:MAX_PERSISTENCE_IDS]


def _require_web_projection(
    *,
    base_url: str,
    timeout_seconds: float,
    policy_version: str,
    policy_sha256: str,
    alert_count: int,
) -> dict[str, float]:
    state_doc, state_ms = _http_get_json(base_url, "/api/v1/state", timeout_seconds)
    if state_doc.get("ok") is not True or not isinstance(state_doc.get("state"), dict):
        raise ValidationError("Web GUI state endpoint does not expose production core state")
    _require_alert_v2_state(
        state_doc["state"],
        policy_version=policy_version,
        policy_sha256=policy_sha256,
        alert_count=alert_count,
    )

    alerts_doc, alerts_ms = _http_get_json(base_url, "/api/v1/alerts", timeout_seconds)
    if alerts_doc.get("ok") is not True:
        raise ValidationError("Web GUI alerts endpoint is not healthy")
    _require_mapped_active_alerts(alerts_doc)

    health_doc, health_ms = _http_get_json(base_url, "/api/v1/health", timeout_seconds)
    if health_doc.get("ok") is not True or health_doc.get("core_available") is not True:
        raise ValidationError("Web GUI health endpoint does not see production core")
    return {"state": state_ms, "alerts": alerts_ms, "health": health_ms}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def _load_baseline(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read Stage 6 baseline {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("stage") != "AlertV2 Stage 6 reboot baseline":
        raise ValidationError("invalid Stage 6 baseline document")
    return payload


def _prepare(args: argparse.Namespace) -> int:
    policy = load_alert_policy(args.policy)
    if policy.alert_count != EXPECTED_ALERT_COUNT:
        raise ValidationError(f"expected {EXPECTED_ALERT_COUNT} policy entries, got {policy.alert_count}")
    core_pid = _require_active_pid("ventilation-core.service")
    agent_pid = _require_active_pid("wvc-service-agent.service")
    runtime = _process_cwd(core_pid)
    expected_runtime = args.expected_runtime.resolve(strict=True)
    if runtime != expected_runtime:
        raise ValidationError(f"production core runtime mismatch: {runtime} != {expected_runtime}")

    client = CoreReadOnlyClient(timeout_seconds=args.core_timeout)
    status = client.request("status")
    safety = require_passive_safe_state(status)
    state = status.get("state")
    if not isinstance(state, dict) or state.get("hardware_ready") is not True:
        raise ValidationError("production core is not hardware_ready")
    _require_alert_v2_state(
        state,
        policy_version=policy.policy_version,
        policy_sha256=policy.sha256,
        alert_count=policy.alert_count,
    )
    alerts = client.request("alerts", limit=200)
    _require_mapped_active_alerts(alerts)
    web_latencies = _require_web_projection(
        base_url=args.web_base_url,
        timeout_seconds=args.web_timeout,
        policy_version=policy.policy_version,
        policy_sha256=policy.sha256,
        alert_count=policy.alert_count,
    )

    baseline = {
        "stage": "AlertV2 Stage 6 reboot baseline",
        "created_unix_ms": int(time.time() * 1000),
        "boot_id": _boot_id(),
        "core_pid": core_pid,
        "service_agent_pid": agent_pid,
        "core_cwd": str(runtime),
        "policy": {
            "path": str(args.policy),
            "policy_version": policy.policy_version,
            "sha256": policy.sha256,
            "alert_count": policy.alert_count,
        },
        "persistence_incident_ids": _incident_ids(alerts),
        "safety": {
            "mode": safety.mode,
            "supply_voltage": safety.supply_voltage,
            "extract_voltage": safety.extract_voltage,
            "output_state_known": safety.output_state_known,
            "control_policy_applied": False,
            "reaction_execution_enabled": False,
        },
        "web": {
            "base_url": args.web_base_url,
            "reachable": True,
            "latency_ms": {key: round(value, 3) for key, value in web_latencies.items()},
        },
    }
    _atomic_write_json(args.baseline, baseline)
    print(json.dumps(baseline, indent=2, sort_keys=True))
    print("PASS: Stage 6 pre-reboot baseline recorded")
    print("PASS: production is STOP / 0 V and AlertV2 remains control-read-only")
    print("PASS: Web GUI state/alerts/health are healthy before reboot")
    print(f"NEXT: reboot CM5, then run Stage 6 verify using baseline {args.baseline}")
    return 0


def _verify(args: argparse.Namespace) -> int:
    if args.duration < 30 or args.duration > 1800:
        raise ValidationError("--duration must be in range 30..1800 seconds")
    if args.interval <= 0 or args.interval > 10:
        raise ValidationError("--interval must be in range (0, 10] seconds")
    baseline = _load_baseline(args.baseline)
    current_boot = _boot_id()
    if current_boot == baseline.get("boot_id"):
        raise ValidationError("boot_id did not change; CM5 has not rebooted since Stage 6 prepare")

    policy = load_alert_policy(args.policy)
    baseline_policy = baseline.get("policy")
    expected_policy = {
        "path": str(args.policy),
        "policy_version": policy.policy_version,
        "sha256": policy.sha256,
        "alert_count": policy.alert_count,
    }
    if baseline_policy != expected_policy:
        raise ValidationError(f"runtime policy changed across reboot: {baseline_policy!r} != {expected_policy!r}")
    if policy.alert_count != EXPECTED_ALERT_COUNT:
        raise ValidationError(f"expected {EXPECTED_ALERT_COUNT} policy entries, got {policy.alert_count}")

    core_pid = _require_active_pid("ventilation-core.service")
    agent_pid = _require_active_pid("wvc-service-agent.service")
    if core_pid == baseline.get("core_pid"):
        raise ValidationError("production core PID did not change across reboot")
    if agent_pid == baseline.get("service_agent_pid"):
        raise ValidationError("Service Agent PID did not change across reboot")
    runtime = _process_cwd(core_pid)
    expected_runtime = args.expected_runtime.resolve(strict=True)
    if runtime != expected_runtime:
        raise ValidationError(f"Stage 5 runtime did not persist across reboot: {runtime} != {expected_runtime}")

    client = CoreReadOnlyClient(timeout_seconds=args.core_timeout)
    status_latencies: list[float] = []
    alerts_latencies: list[float] = []
    web_state_latencies: list[float] = []
    web_alert_latencies: list[float] = []
    web_health_latencies: list[float] = []
    observed_weights: set[int] = set()
    observed_colors: set[str] = set()
    mapped_active_max = 0
    started = time.monotonic()
    samples = 0

    while True:
        if _require_active_pid("ventilation-core.service") != core_pid:
            raise ValidationError("production core PID changed during Stage 6 soak")
        if _require_active_pid("wvc-service-agent.service") != agent_pid:
            raise ValidationError("Service Agent PID changed during Stage 6 soak")

        status = client.request("status")
        safety = require_passive_safe_state(status)
        state = status.get("state")
        if not isinstance(state, dict) or state.get("hardware_ready") is not True:
            raise ValidationError("production hardware_ready is not true during soak")
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
        web = _require_web_projection(
            base_url=args.web_base_url,
            timeout_seconds=args.web_timeout,
            policy_version=policy.policy_version,
            policy_sha256=policy.sha256,
            alert_count=policy.alert_count,
        )
        status_latencies.append(float(status["_latency_ms"]))
        alerts_latencies.append(float(alerts["_latency_ms"]))
        web_state_latencies.append(web["state"])
        web_alert_latencies.append(web["alerts"])
        web_health_latencies.append(web["health"])
        samples += 1

        elapsed = time.monotonic() - started
        if elapsed >= args.duration:
            break
        time.sleep(args.interval)

    final_status = client.request("status")
    final_safety = require_passive_safe_state(final_status)
    final_alerts = client.request("alerts", limit=200)
    _require_mapped_active_alerts(final_alerts)

    before_ids = baseline.get("persistence_incident_ids")
    if not isinstance(before_ids, list) or any(not isinstance(item, int) for item in before_ids):
        raise ValidationError("baseline persistence incident IDs are invalid")
    after_ids = set(_incident_ids(final_alerts))
    missing = [item for item in before_ids if item not in after_ids]
    if missing:
        raise ValidationError(f"alert lifecycle history lost across reboot: missing incident IDs {missing}")

    result = {
        "result": "PASS",
        "stage": "AlertV2 Stage 6 reboot and soak validation",
        "reboot": {
            "boot_id_changed": True,
            "pre_boot_id": baseline.get("boot_id"),
            "post_boot_id": current_boot,
            "pre_core_pid": baseline.get("core_pid"),
            "post_core_pid": core_pid,
            "pre_service_agent_pid": baseline.get("service_agent_pid"),
            "post_service_agent_pid": agent_pid,
            "runtime_persisted": str(runtime),
        },
        "policy": expected_policy,
        "lifecycle": {
            "baseline_incident_ids_checked": before_ids,
            "history_persisted": True,
            "mapped_active_alerts_max": mapped_active_max,
        },
        "runtime": {
            "mode": "read_only_mapping",
            "control_policy_applied": False,
            "reaction_execution_enabled": False,
            "service_plane_correlation": "read_only",
            "observed_active_weights": sorted(observed_weights),
            "observed_hmi_colors": sorted(observed_colors),
        },
        "production": {
            "mode": final_safety.mode,
            "setpoints_v": {
                "supply": final_safety.supply_voltage,
                "extract": final_safety.extract_voltage,
            },
            "output_state_known": final_safety.output_state_known,
            "core_pid_stable_during_soak": True,
            "service_agent_pid_stable_during_soak": True,
        },
        "web_hmi_boundary": {
            "base_url": args.web_base_url,
            "state_get_only": True,
            "alerts_get_only": True,
            "health_get_only": True,
            "core_available": True,
        },
        "latency": {
            "core_status": _latency_summary(status_latencies),
            "core_alerts": _latency_summary(alerts_latencies),
            "web_state": _latency_summary(web_state_latencies),
            "web_alerts": _latency_summary(web_alert_latencies),
            "web_health": _latency_summary(web_health_latencies),
        },
        "safety": {
            "control_commands_sent_by_validator": 0,
            "automatic_alertv2_control_enabled": False,
            "hmi_cm5_communication_watchdog_remains_separate_local_exception": True,
        },
        "samples": samples,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print("PASS: CM5 reboot preserved the Stage 5 AlertV2 production runtime")
    print("PASS: policy version/SHA/count persisted unchanged across reboot")
    print("PASS: alert lifecycle history persisted across reboot")
    print("PASS: core, Service Agent and Web GUI remained stable during soak")
    print("PASS: AlertV2 remained read-only for control; validator sent zero control commands")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.core_timeout <= 0 or args.web_timeout <= 0:
        print("FAIL: timeout arguments must be positive", file=sys.stderr)
        return 2
    try:
        if args.command == "prepare":
            return _prepare(args)
        if args.command == "verify":
            return _verify(args)
        raise ValidationError(f"unsupported command: {args.command}")
    except (ValidationError, Stage4BError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
