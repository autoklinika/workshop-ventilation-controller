from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_WEB_URL = "http://127.0.0.1:18091"
DEFAULT_MAIN_ROOT = Path("/home/wentylacja/workshop-ventilation-controller")
DEFAULT_TELEMETRY_DB = Path("/srv/wvc-data/workshop-ventilation/telemetry.sqlite3")
DEFAULT_ALERT_DB = Path("/srv/wvc-data/workshop-ventilation/alerts.sqlite3")
DEFAULT_AUTOMATION_DB = Path("/var/lib/workshop-ventilation/automation.sqlite3")
DEFAULT_WAKEALARM = Path("/sys/class/rtc/rtc0/wakealarm")

READ_ONLY_ENDPOINTS = (
    "/api/v1/state",
    "/api/v1/control-engine",
    "/api/v1/automation/operator",
    "/api/v1/automation/tuning-validation",
    "/api/v1/calendar",
)


def _http_get_json(base_url: str, path: str) -> dict[str, Any]:
    request = Request(base_url.rstrip("/") + path, method="GET")
    try:
        with urlopen(request, timeout=8.0) as response:
            raw = response.read()
            status = response.status
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "http_status": status, "error": f"invalid JSON: {exc}"}
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "http_status": status,
            "error": "endpoint did not return a JSON object",
        }
    return {"ok": True, "http_status": status, "payload": payload}


def _run_read_only(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc), "command": command}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": command,
    }


def _read_text(path: Path) -> dict[str, Any]:
    try:
        return {"ok": True, "value": path.read_text(encoding="utf-8").strip()}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _file_metadata(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError as exc:
        return {"path": str(path), "exists": False, "error": str(exc)}
    result: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }
    for suffix in ("-wal", "-shm"):
        companion = Path(str(path) + suffix)
        try:
            companion_stat = companion.stat()
        except OSError:
            continue
        result[suffix.removeprefix("-") + "_size_bytes"] = companion_stat.st_size
    return result


def _git_snapshot(root: Path) -> dict[str, Any]:
    return {
        "root": str(root),
        "head": _run_read_only(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "branch": _run_read_only(["git", "-C", str(root), "branch", "--show-current"]),
        "status_short": _run_read_only(["git", "-C", str(root), "status", "--short"]),
    }


def _service_snapshot(unit: str) -> dict[str, Any]:
    active = _run_read_only(["systemctl", "is-active", unit])
    enabled = _run_read_only(["systemctl", "is-enabled", unit])
    pid_result = _run_read_only(["systemctl", "show", unit, "-p", "MainPID", "--value"])
    pid: int | None = None
    cwd: str | None = None
    if pid_result.get("ok"):
        try:
            candidate = int(pid_result.get("stdout") or "0")
        except ValueError:
            candidate = 0
        if candidate > 0:
            pid = candidate
            try:
                cwd = os.path.realpath(f"/proc/{pid}/cwd")
            except OSError:
                cwd = None
    return {
        "unit": unit,
        "active": active,
        "enabled": enabled,
        "main_pid": pid,
        "cwd": cwd,
    }


def _state_payload(api: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    response = api.get("/api/v1/state") or {}
    payload = response.get("payload")
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    state = payload.get("state")
    return state if isinstance(state, dict) else None


def _operator_payload(api: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    response = api.get("/api/v1/automation/operator") or {}
    payload = response.get("payload")
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    operator = payload.get("control_engine_operator")
    return operator if isinstance(operator, dict) else None


def _tuning_payload(api: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    response = api.get("/api/v1/automation/tuning-validation") or {}
    payload = response.get("payload")
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    tuning = payload.get("tuning_validation")
    return tuning if isinstance(tuning, dict) else None


def _first_tacho_zone(shadow: dict[str, Any]) -> dict[str, Any] | None:
    zones = shadow.get("zones")
    if not isinstance(zones, list):
        return None
    for row in zones:
        if isinstance(row, dict) and "tacho_failure_confirmation_seconds" in row:
            return row
    return None


def _safe_preflight(api: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    state = _state_payload(api)
    if state is None:
        blockers.append("STATE_UNAVAILABLE")
        return {"pass": False, "blockers": blockers}

    setpoints = state.get("setpoints")
    if not isinstance(setpoints, dict):
        blockers.append("PHYSICAL_SETPOINTS_MISSING")
    else:
        if setpoints.get("supply_voltage") != 0.0:
            blockers.append("SUPPLY_SETPOINT_NOT_ZERO")
        if setpoints.get("extract_voltage") != 0.0:
            blockers.append("EXTRACT_SETPOINT_NOT_ZERO")

    tacho = state.get("tacho")
    if not isinstance(tacho, dict):
        blockers.append("TACHO_STATE_MISSING")
    else:
        for channel in ("supply", "extract"):
            row = tacho.get(channel)
            if not isinstance(row, dict):
                blockers.append(f"TACHO_{channel.upper()}_MISSING")
                continue
            try:
                rpm = float(row.get("rpm") or 0.0)
            except (TypeError, ValueError):
                blockers.append(f"TACHO_{channel.upper()}_RPM_INVALID")
                continue
            if rpm != 0.0:
                blockers.append(f"TACHO_{channel.upper()}_MOTION_AT_PREFLIGHT")

    shadow = state.get("shadow_automation")
    if not isinstance(shadow, dict):
        blockers.append("SHADOW_AUTOMATION_MISSING")
    else:
        if shadow.get("actuation_supported") is not False:
            blockers.append("ACTUATION_SUPPORTED_NOT_FALSE")
        if shadow.get("operator_mode") != "AUTO":
            blockers.append("OPERATOR_NOT_AUTO")
        readiness = shadow.get("actuation_readiness")
        if not isinstance(readiness, dict):
            blockers.append("ACTUATION_READINESS_MISSING")
        else:
            if readiness.get("actuation_authorized") is not False:
                blockers.append("ACTUATION_AUTHORIZED_NOT_FALSE")
            if readiness.get("ready") is not False:
                blockers.append("READINESS_NOT_FALSE")
        zone = _first_tacho_zone(shadow)
        if zone is None:
            blockers.append("TACHO_CONFIRMATION_MISSING")
        else:
            try:
                confirmation = float(zone.get("tacho_failure_confirmation_seconds"))
            except (TypeError, ValueError):
                confirmation = -1.0
            if abs(confirmation - 4.0) > 1e-9:
                blockers.append("TACHO_CONFIRMATION_NOT_VALIDATED_4S")

    operator = _operator_payload(api)
    if operator is None:
        blockers.append("OPERATOR_API_UNAVAILABLE")
    else:
        intent = operator.get("intent")
        if not isinstance(intent, dict) or intent.get("mode") != "AUTO":
            blockers.append("OPERATOR_INTENT_NOT_AUTO")

    tuning = _tuning_payload(api)
    if tuning is None:
        blockers.append("TUNING_LEDGER_UNAVAILABLE")
    else:
        if tuning.get("total") != 9:
            blockers.append("TUNING_GROUP_COUNT_NOT_9")
        if tuning.get("default_runtime_binding") is not False:
            blockers.append("TUNING_RUNTIME_BOUND")
        if tuning.get("ready_for_actuation_preconditions") is not False:
            blockers.append("ACTUATION_PRECONDITIONS_UNEXPECTEDLY_READY")

    return {"pass": not blockers, "blockers": blockers}


def collect_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    api = {path: _http_get_json(args.web_url, path) for path in READ_ONLY_ENDPOINTS}
    snapshot = {
        "schema_version": 1,
        "kind": "wvc.workshop-commissioning.snapshot",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "web_url": args.web_url,
        "read_only": True,
        "api": api,
        "system": {
            "boot_id": _read_text(Path("/proc/sys/kernel/random/boot_id")),
            "rtc_wakealarm": _read_text(args.wakealarm),
            "ventilation_core": _service_snapshot("ventilation-core.service"),
            "web_ui": _service_snapshot("wvc-web-ui.service"),
            "host_power": _service_snapshot("wvc-host-power.service"),
        },
        "git": _git_snapshot(args.main_root),
        "storage": {
            "telemetry": _file_metadata(args.telemetry_db),
            "alerts": _file_metadata(args.alert_db),
            "automation": _file_metadata(args.automation_db),
        },
    }
    snapshot["safe_preflight"] = _safe_preflight(api)
    return snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a read-only Workshop Ventilation commissioning evidence snapshot. "
            "The tool never writes Control Engine state or actuator outputs."
        )
    )
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--main-root", type=Path, default=DEFAULT_MAIN_ROOT)
    parser.add_argument("--telemetry-db", type=Path, default=DEFAULT_TELEMETRY_DB)
    parser.add_argument("--alert-db", type=Path, default=DEFAULT_ALERT_DB)
    parser.add_argument("--automation-db", type=Path, default=DEFAULT_AUTOMATION_DB)
    parser.add_argument("--wakealarm", type=Path, default=DEFAULT_WAKEALARM)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON evidence snapshot to this path; otherwise print to stdout.",
    )
    parser.add_argument(
        "--require-safe-preflight",
        action="store_true",
        help="Return status 2 unless fail-closed commissioning preflight passes.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    snapshot = collect_snapshot(args)
    encoded = json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"snapshot: {args.output}")
    preflight = snapshot["safe_preflight"]
    if preflight["pass"]:
        print("PASS: commissioning read-only safe preflight")
        return 0
    print("BLOCKED: commissioning safe preflight: " + ", ".join(preflight["blockers"]))
    return 2 if args.require_safe_preflight else 0


if __name__ == "__main__":
    raise SystemExit(main())
