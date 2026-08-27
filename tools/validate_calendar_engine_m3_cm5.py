#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import request as urllib_request
from zoneinfo import ZoneInfo

from ventilation_core.calendar import CalendarConfig, resolve_calendar
from ventilation_core.ctl import send_request


DEFAULT_CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_TIMEZONE = "Europe/Warsaw"


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Calendar Engine M3 on a real CM5 without issuing any ventilation "
            "or AERO control commands."
        )
    )
    parser.add_argument("--phase", choices=("prepare", "verify"), required=True)
    parser.add_argument("--core-socket", type=Path, default=DEFAULT_CORE_SOCKET)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--web-url", default="http://127.0.0.1:18092")
    return parser


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} is not an object")
    return value


def _require_ok(response: dict[str, Any], label: str) -> dict[str, Any]:
    if response.get("ok") is not True:
        raise ValidationError(f"{label} failed: {response.get('error') or response!r}")
    return response


def _core_request(socket_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    command = payload.get("command")
    if command not in {"status", "calendar", "calendar-replace"}:
        raise ValidationError(f"validator attempted forbidden core command: {command!r}")
    return _require_ok(send_request(socket_path, payload), f"core {command}")


def _status(socket_path: Path) -> dict[str, Any]:
    return _require_object(
        _core_request(socket_path, {"command": "status"}).get("state"),
        "state",
    )


def _calendar(socket_path: Path) -> dict[str, Any]:
    return _require_object(
        _core_request(socket_path, {"command": "calendar"}).get("calendar"),
        "calendar",
    )


def _require_non_actuating_safe_state(state: dict[str, Any], label: str) -> None:
    if state.get("mode") != "STOP":
        raise ValidationError(f"{label}: mode is not STOP: {state.get('mode')!r}")
    setpoints = _require_object(state.get("setpoints"), f"{label}.setpoints")
    if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
        raise ValidationError(f"{label}: EC outputs are not 0 V: {setpoints!r}")
    if state.get("output_state_known") is not True:
        raise ValidationError(f"{label}: output_state_known is not true")

    automation = _require_object(state.get("automation"), f"{label}.automation")
    if automation.get("enabled") is not True:
        raise ValidationError(f"{label}: shadow automation is not enabled")
    if automation.get("actuation_supported") is not False:
        raise ValidationError(
            f"{label}: shadow automation unexpectedly supports actuation: {automation!r}"
        )

    tacho = state.get("tacho")
    if isinstance(tacho, dict):
        for channel in ("supply", "extract"):
            row = tacho.get(channel)
            if isinstance(row, dict) and float(row.get("rpm") or 0.0) != 0.0:
                raise ValidationError(f"{label}: {channel} TACHO is not stopped: {row!r}")

    aero = state.get("aero_bus")
    if isinstance(aero, dict):
        telemetry = aero.get("telemetry")
        if isinstance(telemetry, dict):
            for key in ("fan_1_percent", "fan_2_percent"):
                value = telemetry.get(key)
                if value not in (None, 0):
                    raise ValidationError(
                        f"{label}: AERO {key} is not 0%: {telemetry!r}"
                    )


def _canonical_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _profile(
    profile_id: str,
    mode: str,
    *,
    preventilation: int = 0,
    purge: int = 0,
) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "mode": mode,
        "preventilation_minutes": preventilation,
        "purge_minutes": purge,
        "minimum_supply_pct": None,
        "minimum_extract_pct": None,
        "fixed_supply_pct": None,
        "fixed_extract_pct": None,
        "label": profile_id,
    }


def _rule(
    rule_id: str,
    kind: str,
    profile_id: str,
    *,
    weekdays: list[int] | None = None,
    months: list[int] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    start_local: str | None = None,
    end_local: str | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "kind": kind,
        "profile_id": profile_id,
        "weekdays": weekdays or [],
        "months": months or [],
        "start_date": start_date,
        "end_date": end_date,
        "start_local": start_local,
        "end_local": end_local,
        "enabled": True,
        "label": rule_id,
    }


def _semantic_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "timezone": DEFAULT_TIMEZONE,
        "profiles": [
            _profile("WORK", "AUTO", preventilation=30, purge=30),
            _profile("HOLIDAY", "STANDBY"),
        ],
        "rules": [
            _rule(
                "WORKDAY",
                "WEEKLY",
                "WORK",
                weekdays=[1, 2, 3, 4, 5],
                start_local="07:00",
                end_local="17:00",
            ),
            _rule(
                "HOLIDAY_2026_08_28",
                "DATE_EXCEPTION",
                "HOLIDAY",
                start_date="2026-08-28",
                end_date="2026-08-28",
            ),
        ],
    }


def _resolve(config: dict[str, Any], local_iso: str) -> dict[str, Any]:
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    local = datetime.fromisoformat(local_iso).replace(tzinfo=tz)
    resolved = resolve_calendar(
        CalendarConfig.from_dict(config),
        now_utc=local.astimezone(timezone.utc),
    ).to_dict()
    if resolved.get("available") is not True:
        raise ValidationError(f"semantic resolution unavailable at {local_iso}: {resolved!r}")
    return resolved


def _validate_semantic_matrix() -> dict[str, Any]:
    config = _semantic_config()

    pre = _resolve(config, "2026-08-27T06:45:00")
    if pre.get("phase") != "PREVENTILATION" or pre.get("effective_profile") != "WORK":
        raise ValidationError(f"PREVENTILATION semantic check failed: {pre!r}")
    if pre.get("next_transition_reason") != "START_ACTIVE":
        raise ValidationError(f"PREVENTILATION next transition is wrong: {pre!r}")

    active = _resolve(config, "2026-08-27T08:00:00")
    if active.get("phase") != "ACTIVE" or active.get("effective_profile") != "WORK":
        raise ValidationError(f"ACTIVE semantic check failed: {active!r}")

    purge = _resolve(config, "2026-08-27T17:15:00")
    if purge.get("phase") != "PURGE" or purge.get("effective_profile") != "WORK":
        raise ValidationError(f"PURGE semantic check failed: {purge!r}")
    if purge.get("next_transition_reason") != "END_PURGE":
        raise ValidationError(f"PURGE next transition is wrong: {purge!r}")

    exception = _resolve(config, "2026-08-28T10:00:00")
    if exception.get("phase") != "INACTIVE":
        raise ValidationError(f"date exception should be inactive: {exception!r}")
    if exception.get("effective_profile") != "HOLIDAY":
        raise ValidationError(f"date exception profile is wrong: {exception!r}")
    if exception.get("effective_mode") != "STANDBY":
        raise ValidationError(f"date exception mode is wrong: {exception!r}")
    if exception.get("rule_source") != "DATE_EXCEPTION":
        raise ValidationError(f"date exception priority is wrong: {exception!r}")

    wake = _resolve(config, "2026-08-30T12:00:00")
    if wake.get("phase") != "INACTIVE":
        raise ValidationError(f"Sunday should be inactive: {wake!r}")
    if wake.get("next_wake") != "2026-08-31T06:30:00+02:00":
        raise ValidationError(f"next_wake is wrong: {wake!r}")
    if wake.get("next_active_period") != "2026-08-31T07:00:00+02:00":
        raise ValidationError(f"next_active_period is wrong: {wake!r}")

    return {
        "preventilation": pre,
        "active": active,
        "purge": purge,
        "date_exception": exception,
        "next_wake": wake,
    }


def _runtime_safe_config() -> dict[str, Any]:
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    return {
        "schema_version": 1,
        "timezone": DEFAULT_TIMEZONE,
        "profiles": [
            _profile("M3_STANDBY", "STANDBY"),
            _profile("M3_NEXT_WORK", "AUTO", preventilation=30, purge=30),
        ],
        "rules": [
            _rule(
                "M3_TODAY_STANDBY",
                "DATE_EXCEPTION",
                "M3_STANDBY",
                start_date=today.isoformat(),
                end_date=today.isoformat(),
            ),
            _rule(
                "M3_TOMORROW_WORK",
                "DATE_EXCEPTION",
                "M3_NEXT_WORK",
                start_date=tomorrow.isoformat(),
                end_date=tomorrow.isoformat(),
                start_local="12:00",
                end_local="13:00",
            ),
        ],
    }


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=5.0) as response:
            raw = response.read()
    except Exception as exc:
        raise ValidationError(f"{method} {url} failed: {exc}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{method} {url} returned invalid JSON") from exc
    return _require_object(decoded, f"{method} {url} response")


def _web_calendar_get(base_url: str) -> dict[str, Any]:
    response = _http_json("GET", base_url.rstrip("/") + "/api/v1/calendar")
    _require_ok(response, "WebGUI GET calendar")
    return _require_object(response.get("calendar"), "WebGUI calendar")


def _web_calendar_replace(base_url: str, config: dict[str, Any]) -> dict[str, Any]:
    response = _http_json(
        "POST",
        base_url.rstrip("/") + "/api/v1/calendar",
        {"config": config},
    )
    _require_ok(response, "WebGUI POST calendar")
    return _require_object(response.get("calendar"), "WebGUI calendar")


def _write_state_file(
    path: Path,
    *,
    revision: int,
    config: dict[str, Any],
    semantic_matrix: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "revision": revision,
                "config_sha256": _canonical_hash(config),
                "config": config,
                "semantic_matrix": semantic_matrix,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _load_state_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read validation state file {path}: {exc}") from exc
    return _require_object(payload, "validation state")


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    before = _status(args.core_socket)
    _require_non_actuating_safe_state(before, "before Calendar Engine validation")

    semantic_matrix = _validate_semantic_matrix()

    initial_calendar = _calendar(args.core_socket)
    if initial_calendar.get("available") is not True:
        raise ValidationError(f"Calendar Engine is unavailable: {initial_calendar!r}")

    web_initial = _web_calendar_get(args.web_url)
    if web_initial.get("revision") != initial_calendar.get("revision"):
        raise ValidationError(
            "branch WebGUI does not project the same Calendar Engine revision as core"
        )

    config = _runtime_safe_config()
    replaced = _web_calendar_replace(args.web_url, config)
    revision = replaced.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 2:
        raise ValidationError(f"invalid Calendar Engine revision after replace: {revision!r}")
    replaced_config = _require_object(replaced.get("config"), "replaced config")
    if _canonical_hash(replaced_config) != _canonical_hash(config):
        raise ValidationError("WebGUI calendar replace did not preserve sanitized config")

    readback = _calendar(args.core_socket)
    if readback.get("revision") != revision:
        raise ValidationError("core calendar revision differs after WebGUI replace")
    readback_config = _require_object(readback.get("config"), "readback config")
    if _canonical_hash(readback_config) != _canonical_hash(config):
        raise ValidationError("core calendar readback differs after WebGUI replace")

    state = _status(args.core_socket)
    _require_non_actuating_safe_state(state, "after Calendar Engine validation")
    calendar_state = _require_object(state.get("calendar"), "state.calendar")
    if calendar_state.get("effective_profile") != "M3_STANDBY":
        raise ValidationError(f"runtime safe calendar profile is wrong: {calendar_state!r}")
    if calendar_state.get("effective_mode") != "STANDBY":
        raise ValidationError(f"runtime safe calendar mode is wrong: {calendar_state!r}")
    if calendar_state.get("rule_source") != "DATE_EXCEPTION":
        raise ValidationError(f"runtime safe calendar source is wrong: {calendar_state!r}")

    web_final = _web_calendar_get(args.web_url)
    if web_final.get("revision") != revision:
        raise ValidationError("branch WebGUI final revision differs from core")

    _write_state_file(
        args.state_file,
        revision=revision,
        config=config,
        semantic_matrix=semantic_matrix,
    )
    return {
        "phase": "prepare",
        "calendar_revision": revision,
        "config_sha256": _canonical_hash(config),
        "semantic_checks": {
            "preventilation": "PASS",
            "active": "PASS",
            "purge": "PASS",
            "date_exception": "PASS",
            "next_wake": "PASS",
        },
        "webgui_roundtrip": "PASS",
        "physical_actuation": False,
        "runtime_mode": state.get("mode"),
        "runtime_setpoints": state.get("setpoints"),
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    expected = _load_state_file(args.state_file)
    expected_config = _require_object(expected.get("config"), "expected config")
    expected_revision = expected.get("revision")
    expected_hash = expected.get("config_sha256")
    if not isinstance(expected_revision, int) or expected_revision < 1:
        raise ValidationError(f"invalid expected revision: {expected_revision!r}")
    if not isinstance(expected_hash, str):
        raise ValidationError("missing expected config hash")

    state = _status(args.core_socket)
    _require_non_actuating_safe_state(state, "after Calendar Engine core restart")

    readback = _calendar(args.core_socket)
    if readback.get("revision") != expected_revision:
        raise ValidationError(
            "Calendar Engine revision did not persist: "
            f"{readback.get('revision')!r} != {expected_revision!r}"
        )
    config = _require_object(readback.get("config"), "persisted config")
    actual_hash = _canonical_hash(config)
    if actual_hash != expected_hash or actual_hash != _canonical_hash(expected_config):
        raise ValidationError("Calendar Engine config did not persist byte-semantically")

    web = _web_calendar_get(args.web_url)
    if web.get("revision") != expected_revision:
        raise ValidationError("branch WebGUI did not recover persisted calendar revision")
    web_config = _require_object(web.get("config"), "WebGUI persisted config")
    if _canonical_hash(web_config) != expected_hash:
        raise ValidationError("branch WebGUI did not recover persisted calendar config")

    calendar_state = _require_object(state.get("calendar"), "state.calendar")
    if calendar_state.get("effective_profile") != "M3_STANDBY":
        raise ValidationError(f"persisted runtime profile is wrong: {calendar_state!r}")
    if calendar_state.get("effective_mode") != "STANDBY":
        raise ValidationError(f"persisted runtime mode is wrong: {calendar_state!r}")

    return {
        "phase": "verify",
        "persistence": "PASS",
        "calendar_revision": expected_revision,
        "config_sha256": expected_hash,
        "webgui_recovery": "PASS",
        "physical_actuation": False,
        "runtime_mode": state.get("mode"),
        "runtime_setpoints": state.get("setpoints"),
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prepare(args) if args.phase == "prepare" else verify(args)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"ok": True, "validation": "calendar_engine_m3_cm5", **result},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    print(f"PASS: Calendar Engine M3 CM5 {args.phase} phase")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
