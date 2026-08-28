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
        with urlopen(request, timeout=6.0) as response:
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
        with urlopen(request, timeout=6.0) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValidationError(f"HTTP GET {path} failed: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"HTTP GET {path} was not UTF-8") from exc


def _zone(shadow: dict[str, Any]) -> dict[str, Any]:
    zones = shadow.get("zones")
    if not isinstance(zones, list) or not zones:
        raise ValidationError("SHADOW state has no zones")
    for row in zones:
        if isinstance(row, dict) and "tacho_supply_status" in row:
            return row
    first = zones[0]
    if not isinstance(first, dict):
        raise ValidationError("SHADOW zone is not an object")
    return first


def _require_non_actuating_state(
    state: dict[str, Any],
    *,
    expected_operator_mode: str,
    require_validated_tacho_confirmation: bool = True,
) -> dict[str, Any]:
    setpoints = state.get("setpoints")
    if not isinstance(setpoints, dict):
        raise ValidationError("state has no physical setpoints object")
    if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
        raise ValidationError(f"physical EC setpoints are not 0 V: {setpoints!r}")

    tacho = state.get("tacho")
    if isinstance(tacho, dict):
        for channel in ("supply", "extract"):
            row = tacho.get(channel)
            if isinstance(row, dict) and float(row.get("rpm") or 0.0) != 0.0:
                raise ValidationError(f"{channel} reports physical fan motion: {row!r}")

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

    readiness = shadow.get("actuation_readiness")
    if not isinstance(readiness, dict):
        raise ValidationError("SHADOW has no actuation_readiness object")
    if readiness.get("actuation_authorized") is not False:
        raise ValidationError("actuation readiness unexpectedly has authority")
    if readiness.get("ready") is not False:
        raise ValidationError("actuation readiness unexpectedly reports ready=true")

    zone = _zone(shadow)
    if require_validated_tacho_confirmation:
        confirmation = zone.get("tacho_failure_confirmation_seconds")
        if confirmation is None or abs(float(confirmation) - 4.0) > 1e-9:
            raise ValidationError(
                f"validated TACHO confirmation is not 4.0 s in live SHADOW state: {confirmation!r}"
            )
    return zone


def _operator(web_url: str) -> dict[str, Any]:
    payload = _request_json(web_url, "/api/v1/automation/operator")
    operator = payload.get("control_engine_operator")
    if not isinstance(operator, dict):
        raise ValidationError(
            "WebGUI did not normalize real core operator projection to control_engine_operator"
        )
    intent = operator.get("intent")
    if not isinstance(intent, dict):
        raise ValidationError(f"operator intent is missing: {operator!r}")
    return operator


def _calendar(web_url: str) -> dict[str, Any]:
    calendar = _request_json(web_url, "/api/v1/calendar").get("calendar")
    if not isinstance(calendar, dict):
        raise ValidationError("Calendar Engine WebAPI projection is missing")
    if calendar.get("available") is not True:
        raise ValidationError(f"Calendar Engine is not available: {calendar!r}")
    if not isinstance(calendar.get("config"), dict):
        raise ValidationError("Calendar Engine projection has no config")
    if isinstance(calendar.get("revision"), bool) or not isinstance(calendar.get("revision"), int):
        raise ValidationError(f"Calendar Engine revision is invalid: {calendar.get('revision')!r}")
    return calendar


def _validate_ledger(web_url: str) -> None:
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
    print("PASS: tuning ledger remains read-only/unbound and reports exactly 1/9 complete")


def _validate_html(web_url: str) -> None:
    html = _request_text(web_url, "/automation")
    required = (
        "SHADOW — BRAK STEROWANIA FIZYCZNYMI WYJŚCIAMI",
        'data-automation-tab="state"',
        'data-automation-tab="schedule"',
        'data-automation-tab="manual"',
        'data-automation-tab="tuning"',
        'src="/automation.js"',
        'src="/calendar.js"',
    )
    missing = [marker for marker in required if marker not in html]
    if missing:
        raise ValidationError(f"/automation is missing required UI markers: {missing!r}")
    print("PASS: /automation serves Stage1 four-tab SHADOW UI on the real-core runtime")


def prepare(web_url: str, state_file: Path) -> None:
    _validate_html(web_url)

    initial_state = _request_json(web_url, "/api/v1/state").get("state")
    if not isinstance(initial_state, dict):
        raise ValidationError("initial state payload is missing")
    initial_zone = _require_non_actuating_state(initial_state, expected_operator_mode="AUTO")
    print(
        "PASS: real ventilation-core state reached WebGUI; AUTO SHADOW / EC=0 V / "
        f"TACHO confirmation={initial_zone.get('tacho_failure_confirmation_seconds')} s"
    )

    initial_operator = _operator(web_url)
    initial_revision = initial_operator.get("revision")
    if (initial_operator.get("intent") or {}).get("mode") != "AUTO":
        raise ValidationError(f"initial real-core operator is not AUTO: {initial_operator!r}")
    if initial_operator.get("persistent") is not False:
        raise ValidationError(f"operator intent unexpectedly reports persistence: {initial_operator!r}")
    print("PASS: WebGUI normalized the real core operator response and initial intent is volatile AUTO")

    calendar_before = _calendar(web_url)
    calendar_config = calendar_before["config"]
    revision_before = calendar_before["revision"]
    calendar_after = _request_json(
        web_url,
        "/api/v1/calendar",
        method="POST",
        payload={"config": calendar_config},
    ).get("calendar")
    if not isinstance(calendar_after, dict):
        raise ValidationError("Calendar Engine round-trip write returned no calendar object")
    if calendar_after.get("config") != calendar_config:
        raise ValidationError("Calendar Engine round-trip changed configuration")
    if calendar_after.get("revision") != revision_before + 1:
        raise ValidationError(
            "Calendar Engine revision did not advance exactly once through WebGUI: "
            f"before={revision_before!r} after={calendar_after.get('revision')!r}"
        )
    print(
        "PASS: Harmonogram WebGUI -> real Calendar Engine round-trip succeeded in isolated DB; "
        f"revision {revision_before} -> {calendar_after['revision']}"
    )

    _validate_ledger(web_url)

    manual_intent = {
        "mode": "MANUAL",
        "manual_supply_pct": 37.0,
        "manual_extract_pct": 43.0,
        "manual_aero_speed": 2,
    }
    _request_json(
        web_url,
        "/api/v1/automation/operator",
        method="POST",
        payload=manual_intent,
    )
    manual_operator = _operator(web_url)
    if (manual_operator.get("intent") or {}) != manual_intent:
        raise ValidationError(f"real core MANUAL intent mismatch: {manual_operator!r}")
    manual_state = _request_json(web_url, "/api/v1/state").get("state")
    if not isinstance(manual_state, dict):
        raise ValidationError("MANUAL state payload is missing")
    _require_non_actuating_state(manual_state, expected_operator_mode="MANUAL")
    print("PASS: MANUAL from WebGUI reached real Control Engine SHADOW; physical EC remained 0 V")

    _request_json(
        web_url,
        "/api/v1/automation/operator",
        method="POST",
        payload={"mode": "AUTO"},
    )
    auto_operator = _operator(web_url)
    if (auto_operator.get("intent") != {"mode": "AUTO"}:
        raise ValidationError(f"real core did not return to canonical AUTO: {auto_operator!r}")
    if (
        isinstance(initial_revision, int)
        and isinstance(auto_operator.get("revision"), int)
        and auto_operator["revision"] <= initial_revision
    ):
        raise ValidationError(
            f"operator revision did not advance across MANUAL -> AUTO: {auto_operator!r}"
        )
    final_state = _request_json(web_url, "/api/v1/state").get("state")
    if not isinstance(final_state, dict):
        raise ValidationError("final AUTO state payload is missing")
    _require_non_actuating_state(final_state, expected_operator_mode="AUTO")
    print("PASS: AUTO restore reached real Control Engine and remained non-actuating")

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "calendar_revision": calendar_after["revision"],
                "calendar_config": calendar_config,
                "operator_revision_before_restart": auto_operator.get("revision"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def verify(web_url: str, state_file: Path) -> None:
    try:
        expected = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read Stage2 state file: {exc}") from exc
    if not isinstance(expected, dict):
        raise ValidationError("Stage2 state file is not an object")

    state = _request_json(web_url, "/api/v1/state").get("state")
    if not isinstance(state, dict):
        raise ValidationError("post-restart state payload is missing")
    _require_non_actuating_state(state, expected_operator_mode="AUTO")

    operator = _operator(web_url)
    if operator.get("intent") != {"mode": "AUTO"}:
        raise ValidationError(f"operator intent did not fail-open to AUTO after restart: {operator!r}")
    if operator.get("persistent") is not False:
        raise ValidationError(f"operator unexpectedly became persistent: {operator!r}")
    if operator.get("revision") != 0:
        raise ValidationError(
            "volatile operator revision did not reset on real core restart: "
            f"{operator.get('revision')!r}"
        )
    print("PASS: real core restart cleared volatile operator history and returned to AUTO revision 0")

    calendar = _calendar(web_url)
    if calendar.get("revision") != expected.get("calendar_revision"):
        raise ValidationError(
            "Calendar revision did not persist across real core restart: "
            f"expected={expected.get('calendar_revision')!r} actual={calendar.get('revision')!r}"
        )
    if calendar.get("config") != expected.get("calendar_config"):
        raise ValidationError("Calendar configuration did not persist across real core restart")
    print(
        "PASS: Calendar Engine isolated persistence survived real core restart; "
        f"revision={calendar['revision']}"
    )

    _validate_ledger(web_url)
    print("PASS: post-restart WebGUI remains bound to real non-actuating Control Engine runtime")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate WebGUI Automation Stage2 against the real CM5 Control Engine runtime"
    )
    parser.add_argument("--phase", choices=("prepare", "verify"), required=True)
    parser.add_argument("--web-url", required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.phase == "prepare":
        prepare(args.web_url, args.state_file)
    else:
        verify(args.web_url, args.state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
