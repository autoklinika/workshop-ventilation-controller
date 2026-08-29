from __future__ import annotations

import argparse
import json
from pathlib import Path

import validate_web_gui_automation_stage2_runtime_cm5 as stage2


class ValidationError(RuntimeError):
    pass


def _load_expected(state_file: Path) -> dict:
    try:
        value = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read Stage3 state file: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Stage3 state file is not an object")
    return value


def prepare(web_url: str, state_file: Path) -> None:
    stage2.prepare(web_url, state_file)
    print("PASS: Stage3 prepare completed through the real systemd WebGUI client")


def verify_web_restart(web_url: str, state_file: Path) -> None:
    expected = _load_expected(state_file)
    stage2._validate_html(web_url)

    state = stage2._request_json(web_url, "/api/v1/state").get("state")
    if not isinstance(state, dict):
        raise ValidationError("post-WebGUI-restart state payload is missing")
    stage2._require_non_actuating_state(state, expected_operator_mode="AUTO")

    operator = stage2._operator(web_url)
    stage2._require_auto_operator(operator, label="post-WebGUI-restart operator")
    if operator.get("revision") != expected.get("operator_revision_before_restart"):
        raise ValidationError(
            "WebGUI restart changed core-owned volatile operator revision: "
            f"expected={expected.get('operator_revision_before_restart')!r} "
            f"actual={operator.get('revision')!r}"
        )

    calendar = stage2._calendar(web_url)
    if calendar.get("revision") != expected.get("calendar_revision"):
        raise ValidationError(
            "WebGUI restart changed core-owned Calendar revision: "
            f"expected={expected.get('calendar_revision')!r} actual={calendar.get('revision')!r}"
        )
    if calendar.get("config") != expected.get("calendar_config"):
        raise ValidationError("WebGUI restart changed core-owned Calendar configuration")

    stage2._validate_ledger(web_url)
    print(
        "PASS: restarting wvc-web-ui.service preserved authoritative core operator, "
        "Calendar Engine state, and SHADOW safety"
    )


def verify_core_restart(web_url: str, state_file: Path) -> None:
    stage2.verify(web_url, state_file)
    print("PASS: Stage3 systemd WebGUI stayed a client across authoritative core restart")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate WebGUI Automation Stage3 through the real wvc-web-ui.service"
    )
    parser.add_argument(
        "--phase",
        choices=("prepare", "web-restart", "core-restart"),
        required=True,
    )
    parser.add_argument("--web-url", required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.phase == "prepare":
        prepare(args.web_url, args.state_file)
    elif args.phase == "web-restart":
        verify_web_restart(args.web_url, args.state_file)
    else:
        verify_core_restart(args.web_url, args.state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
