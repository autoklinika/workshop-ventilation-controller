from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ValidationError(RuntimeError):
    pass


def _request_json(
    web_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        web_url.rstrip("/") + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=4.0) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValidationError(f"HTTP {method} {path} failed: {exc}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"HTTP {method} {path} returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValidationError(f"HTTP {method} {path} did not return an object")
    if decoded.get("ok") is not True:
        raise ValidationError(f"HTTP {method} {path} rejected request: {decoded!r}")
    return decoded


def _request_text(web_url: str, path: str) -> str:
    request = Request(web_url.rstrip("/") + path, method="GET")
    try:
        with urlopen(request, timeout=4.0) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValidationError(f"HTTP GET {path} failed: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"HTTP GET {path} was not UTF-8") from exc


def _require_non_actuating_state(
    state: dict[str, Any],
    *,
    expected_operator_mode: str,
) -> None:
    setpoints = state.get("setpoints")
    if not isinstance(setpoints, dict):
        raise ValidationError("state has no physical setpoints object")
    if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
        raise ValidationError(f"validation fixture physical setpoints are not 0 V: {setpoints!r}")

    shadow = state.get("shadow_automation")
    if not isinstance(shadow, dict):
        raise ValidationError("state has no shadow_automation object")
    if shadow.get("actuation_supported") is not False:
        raise ValidationError("Control Engine SHADOW unexpectedly supports actuation")
    if shadow.get("operator_mode") != expected_operator_mode:
        raise ValidationError(
            f"operator mode mismatch: expected {expected_operator_mode}, "
            f"got {shadow.get('operator_mode')!r}"
        )


def _read_command_log(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read fake-core command log: {exc}") from exc
    commands: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"invalid fake-core command log line: {line!r}") from exc
        if not isinstance(row, dict):
            raise ValidationError("fake-core command log contains non-object entry")
        commands.append(row)
    return commands


def _validate_command_boundary(commands: list[dict[str, Any]]) -> None:
    allowed = {
        "status",
        "calendar",
        "control-engine-operator",
        "control-engine-operator-replace",
    }
    observed = {row.get("command") for row in commands}
    forbidden = sorted(value for value in observed if value not in allowed)
    if forbidden:
        raise ValidationError(f"WebGUI crossed SHADOW command boundary: {forbidden!r}")

    replacements = [
        row for row in commands if row.get("command") == "control-engine-operator-replace"
    ]
    expected_manual = {
        "command": "control-engine-operator-replace",
        "operator": {
            "mode": "MANUAL",
            "manual_supply_pct": 37.0,
            "manual_extract_pct": 43.0,
            "manual_aero_speed": 2,
        },
    }
    expected_auto = {
        "command": "control-engine-operator-replace",
        "operator": {"mode": "AUTO"},
    }
    if replacements != [expected_manual, expected_auto]:
        raise ValidationError(
            "operator command boundary is not canonical MANUAL -> AUTO: "
            f"{replacements!r}"
        )


def validate(web_url: str, command_log: Path) -> None:
    html = _request_text(web_url, "/automation")
    required_html = (
        "SHADOW — BRAK STEROWANIA FIZYCZNYMI WYJŚCIAMI",
        'data-automation-tab="state"',
        'data-automation-tab="schedule"',
        'data-automation-tab="manual"',
        'data-automation-tab="tuning"',
        'src="/automation.js"',
        'src="/calendar.js"',
    )
    missing = [marker for marker in required_html if marker not in html]
    if missing:
        raise ValidationError(f"/automation is missing required UI markers: {missing!r}")
    print("PASS: /automation serves four-tab SHADOW UI and shared Calendar client")

    initial_state = _request_json(web_url, "/api/v1/state")["state"]
    if not isinstance(initial_state, dict):
        raise ValidationError("state payload is not an object")
    _require_non_actuating_state(initial_state, expected_operator_mode="AUTO")
    print("PASS: initial WebGUI state is AUTO SHADOW with physical fixture at 0 V")

    calendar = _request_json(web_url, "/api/v1/calendar").get("calendar")
    if not isinstance(calendar, dict):
        raise ValidationError("Calendar Engine WebAPI projection is missing")
    print("PASS: existing Calendar Engine endpoint is reachable through the staged WebGUI")

    ledger = _request_json(web_url, "/api/v1/automation/tuning-validation").get(
        "tuning_validation"
    )
    if not isinstance(ledger, dict):
        raise ValidationError("tuning validation payload is missing")
    if ledger.get("completed") != 1 or ledger.get("total") != 9:
        raise ValidationError(f"unexpected tuning progress: {ledger!r}")
    if ledger.get("default_runtime_binding") is not False:
        raise ValidationError("tuning validation profile unexpectedly reports runtime binding")
    if ledger.get("ready_for_actuation_preconditions") is not False:
        raise ValidationError("tuning profile unexpectedly satisfies actuation preconditions")
    groups = ledger.get("groups")
    if not isinstance(groups, list):
        raise ValidationError("tuning groups are missing")
    satisfied = [row.get("id") for row in groups if isinstance(row, dict) and row.get("satisfied")]
    if satisfied != ["tacho_confirmation"]:
        raise ValidationError(f"unexpected satisfied tuning groups: {satisfied!r}")
    print("PASS: tuning ledger is read-only, unbound and reports exactly 1/9 complete")

    initial_operator = _request_json(web_url, "/api/v1/automation/operator").get(
        "control_engine_operator"
    )
    if not isinstance(initial_operator, dict) or (initial_operator.get("intent") or {}).get("mode") != "AUTO":
        raise ValidationError(f"initial operator intent is not AUTO: {initial_operator!r}")

    manual = {
        "mode": "MANUAL",
        "manual_supply_pct": 37.0,
        "manual_extract_pct": 43.0,
        "manual_aero_speed": 2,
    }
    _request_json(
        web_url,
        "/api/v1/automation/operator",
        method="POST",
        payload=manual,
    )
    manual_state = _request_json(web_url, "/api/v1/state")["state"]
    _require_non_actuating_state(manual_state, expected_operator_mode="MANUAL")
    print("PASS: MANUAL operator intent changes SHADOW state only; fixture remains 0 V")

    _request_json(
        web_url,
        "/api/v1/automation/operator",
        method="POST",
        payload={"mode": "AUTO"},
    )
    final_operator = _request_json(web_url, "/api/v1/automation/operator").get(
        "control_engine_operator"
    )
    if not isinstance(final_operator, dict) or (final_operator.get("intent") or {}).get("mode") != "AUTO":
        raise ValidationError(f"operator intent did not return to AUTO: {final_operator!r}")
    final_state = _request_json(web_url, "/api/v1/state")["state"]
    _require_non_actuating_state(final_state, expected_operator_mode="AUTO")
    print("PASS: AUTO restore is visible through WebGUI and remains non-actuating")

    commands = _read_command_log(command_log)
    _validate_command_boundary(commands)
    print("PASS: fake-core log contains only status/calendar/operator SHADOW commands")
    print("PASS: AUTO payload is canonical {\"mode\":\"AUTO\"}; no stale MANUAL null fields")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate WebGUI Automation Stage1 on CM5 without touching physical control"
    )
    parser.add_argument("--web-url", required=True)
    parser.add_argument("--command-log", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    validate(args.web_url, args.command_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
