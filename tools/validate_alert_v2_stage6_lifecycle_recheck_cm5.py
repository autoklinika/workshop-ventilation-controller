#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ventilation_core.alert_policy import load_alert_policy
from ventilation_core.alert_v2_stage4b_runtime import (
    CoreReadOnlyClient,
    Stage4BError,
    require_passive_safe_state,
)


DEFAULT_BASELINE = Path("/var/lib/workshop-ventilation/alert-v2-stage6-reboot-baseline.json")
DEFAULT_POLICY = Path("/etc/workshop-ventilation/alerts-v2.toml")
DEFAULT_EXPECTED_RUNTIME = Path("/home/wentylacja/wvc-alert-v2-stage4")
EXPECTED_ALERT_COUNT = 49
ALERT_HISTORY_LIMIT = 1000


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AlertV2 Stage 6: re-check reboot alert-history persistence against the full "
            "read-only core history window after the initial top-50 validator false negative"
        )
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--expected-runtime", type=Path, default=DEFAULT_EXPECTED_RUNTIME)
    parser.add_argument("--core-timeout", type=float, default=3.0)
    return parser


def _systemctl_pid(unit: str) -> int:
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", unit],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3.0,
    )
    if active.returncode != 0:
        raise ValidationError(f"required service is not active: {unit}")
    completed = subprocess.run(
        ["systemctl", "show", unit, "-p", "MainPID", "--value"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=3.0,
    )
    if completed.returncode != 0:
        raise ValidationError(f"cannot read MainPID for {unit}: {completed.stderr.strip()}")
    try:
        pid = int(completed.stdout.strip())
    except ValueError as exc:
        raise ValidationError(f"invalid MainPID for {unit}: {completed.stdout.strip()!r}") from exc
    if pid < 1:
        raise ValidationError(f"invalid MainPID for {unit}: {pid}")
    return pid


def _load_baseline(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read Stage 6 baseline {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("stage") != "AlertV2 Stage 6 reboot baseline":
        raise ValidationError("invalid Stage 6 baseline document")
    ids = payload.get("persistence_incident_ids")
    if not isinstance(ids, list) or not ids or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in ids
    ):
        raise ValidationError("baseline persistence incident IDs are invalid")
    return payload


def _boot_id() -> str:
    value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    if not value:
        raise ValidationError("kernel boot_id is empty")
    return value


def _record_id(record: dict[str, Any]) -> int | None:
    raw = record.get("id", record.get("alert_id"))
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    return None


def _all_incident_records(document: dict[str, Any]) -> dict[int, dict[str, Any]]:
    active = document.get("active")
    history = document.get("history")
    if not isinstance(active, list) or not isinstance(history, list):
        raise ValidationError("alerts response missing active/history lists")

    result: dict[int, dict[str, Any]] = {}
    for section_name, records in (("active", active), ("history", history)):
        for raw in records:
            if not isinstance(raw, dict):
                continue
            incident_id = _record_id(raw)
            if incident_id is None:
                continue
            record = dict(raw)
            record["_section"] = section_name
            result[incident_id] = record
    return result


def _require_read_only_runtime(state: dict[str, Any], policy_version: str, sha256: str) -> dict[str, Any]:
    alert_v2 = state.get("alert_v2")
    if not isinstance(alert_v2, dict):
        raise ValidationError("production state does not expose alert_v2")
    expected = {
        "runtime_mode": "read_only_mapping",
        "loaded": True,
        "policy_version": policy_version,
        "sha256": sha256,
        "alert_count": EXPECTED_ALERT_COUNT,
        "control_policy_applied": False,
        "unmapped_active_alerts": 0,
    }
    actual = {key: alert_v2.get(key) for key in expected}
    if actual != expected:
        raise ValidationError(f"unexpected AlertV2 runtime state: {actual!r}")
    service_plane = alert_v2.get("service_plane")
    if not isinstance(service_plane, dict) or service_plane.get("control_policy_applied") is not False:
        raise ValidationError("Service Plane control policy is not read-only")
    correlation = service_plane.get("correlation")
    if not isinstance(correlation, dict) or correlation.get("mode") != "read_only":
        raise ValidationError("Service Plane correlation is not read-only")
    return alert_v2


def main() -> int:
    args = build_parser().parse_args()
    if args.core_timeout <= 0:
        print("FAIL: --core-timeout must be positive", file=sys.stderr)
        return 2

    try:
        baseline = _load_baseline(args.baseline)
        current_boot = _boot_id()
        if current_boot == baseline.get("boot_id"):
            raise ValidationError("boot_id did not change; reboot persistence cannot be validated")

        policy = load_alert_policy(args.policy)
        if policy.alert_count != EXPECTED_ALERT_COUNT:
            raise ValidationError(
                f"expected {EXPECTED_ALERT_COUNT} policy entries, got {policy.alert_count}"
            )
        baseline_policy = baseline.get("policy")
        expected_policy = {
            "path": str(args.policy),
            "policy_version": policy.policy_version,
            "sha256": policy.sha256,
            "alert_count": policy.alert_count,
        }
        if baseline_policy != expected_policy:
            raise ValidationError(
                f"runtime policy changed across reboot: {baseline_policy!r} != {expected_policy!r}"
            )

        core_pid = _systemctl_pid("ventilation-core.service")
        agent_pid = _systemctl_pid("wvc-service-agent.service")
        runtime = Path(f"/proc/{core_pid}/cwd").resolve(strict=True)
        expected_runtime = args.expected_runtime.resolve(strict=True)
        if runtime != expected_runtime:
            raise ValidationError(f"production runtime mismatch: {runtime} != {expected_runtime}")

        client = CoreReadOnlyClient(timeout_seconds=args.core_timeout)
        status = client.request("status")
        safety = require_passive_safe_state(status)
        state = status.get("state")
        if not isinstance(state, dict) or state.get("hardware_ready") is not True:
            raise ValidationError("production core is not hardware_ready")
        _require_read_only_runtime(state, policy.policy_version, policy.sha256)

        alerts = client.request("alerts", limit=ALERT_HISTORY_LIMIT)
        records = _all_incident_records(alerts)
        before_ids = baseline["persistence_incident_ids"]
        missing = [incident_id for incident_id in before_ids if incident_id not in records]
        if missing:
            raise ValidationError(
                "alert lifecycle history really is missing baseline incidents from the full "
                f"{ALERT_HISTORY_LIMIT}-record read-only window: {missing}"
            )

        matched = []
        for incident_id in before_ids:
            record = records[incident_id]
            matched.append(
                {
                    "id": incident_id,
                    "code": record.get("code"),
                    "state": record.get("state"),
                    "section": record.get("_section"),
                }
            )

        result = {
            "result": "PASS",
            "stage": "AlertV2 Stage 6 lifecycle persistence recheck",
            "reason_for_recheck": (
                "initial validator compared a top-50 baseline with a new top-50 post-reboot "
                "window; new incidents can shift the oldest baseline IDs out of that window"
            ),
            "reboot": {
                "boot_id_changed": True,
                "pre_boot_id": baseline.get("boot_id"),
                "post_boot_id": current_boot,
                "pre_core_pid": baseline.get("core_pid"),
                "post_core_pid": core_pid,
                "pre_service_agent_pid": baseline.get("service_agent_pid"),
                "post_service_agent_pid": agent_pid,
            },
            "runtime": {
                "core_cwd": str(runtime),
                "mode": "read_only_mapping",
                "control_policy_applied": False,
                "reaction_execution_enabled": False,
            },
            "safety": {
                "mode": safety.mode,
                "supply_voltage": safety.supply_voltage,
                "extract_voltage": safety.extract_voltage,
                "output_state_known": safety.output_state_known,
                "control_commands_sent_by_validator": 0,
            },
            "persistence": {
                "history_request_limit": ALERT_HISTORY_LIMIT,
                "returned_unique_incident_ids": len(records),
                "baseline_incident_ids_checked": len(before_ids),
                "missing_baseline_incident_ids": [],
                "matched_baseline_incidents": matched,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        print("PASS: every Stage 6 baseline incident is still present after reboot")
        print("PASS: IDs shifted out of the previous top-50 window were not lost")
        print("PASS: production remains STOP / 0 V and AlertV2 remains control-read-only")
        print("PASS: validator used only status/alerts reads and sent zero control commands")
        return 0
    except (ValidationError, Stage4BError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
