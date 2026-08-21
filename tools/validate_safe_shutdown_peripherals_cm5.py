#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from ventilation_core.host_power_agent import DEFAULT_CORE_SOCKET, HostPowerAgent


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Physically validate the PR #77 peripheral-off sequence against the live "
            "CM5 core without executing host poweroff"
        )
    )
    parser.add_argument(
        "--confirm-active-output-test",
        action="store_true",
        help=(
            "Required acknowledgement that this test will actively command both EC fan "
            "outputs to STOP/0 V and the AERO recuperator to airing OFF / speed 0"
        ),
    )
    parser.add_argument("--core-socket", type=Path, default=DEFAULT_CORE_SOCKET)
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
    completed = subprocess.run(
        ["systemctl", "is-active", "--quiet", unit],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3.0,
    )
    if completed.returncode != 0:
        raise ValidationError(f"required production service is not active: {unit}")
    raw = _systemctl_value(unit, "MainPID")
    try:
        pid = int(raw)
    except ValueError as exc:
        raise ValidationError(f"invalid MainPID for {unit}: {raw!r}") from exc
    if pid < 1:
        raise ValidationError(f"invalid MainPID for {unit}: {pid}")
    return pid


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} is not an object")
    return value


def _require_final_safe_state(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("ok") is not True:
        raise ValidationError(f"final core status failed: {status.get('error')!r}")
    state = _require_object(status.get("state"), "state")
    if state.get("mode") != "STOP":
        raise ValidationError(f"final mode is not STOP: {state.get('mode')!r}")
    setpoints = _require_object(state.get("setpoints"), "setpoints")
    if setpoints.get("supply_voltage") != 0.0:
        raise ValidationError(
            f"final supply output is not 0 V: {setpoints.get('supply_voltage')!r}"
        )
    if setpoints.get("extract_voltage") != 0.0:
        raise ValidationError(
            f"final extract output is not 0 V: {setpoints.get('extract_voltage')!r}"
        )
    if state.get("output_state_known") is not True:
        raise ValidationError("final fan output state is not confirmed")

    aero = _require_object(state.get("aero_bus"), "aero_bus")
    if aero.get("ready") is not True or aero.get("worker_alive") is not True:
        raise ValidationError("AERO worker is not ready/alive after shutdown preparation")
    if aero.get("online") is not True or aero.get("usable") is not True:
        raise ValidationError("AERO is not online+usable after shutdown preparation")
    result = _require_object(aero.get("last_control_result"), "aero_bus.last_control_result")
    if result.get("kind") != "speed":
        raise ValidationError(f"final AERO result is not speed: {result.get('kind')!r}")
    if result.get("target_value") != 0:
        raise ValidationError(
            f"final AERO result does not target speed 0: {result.get('target_value')!r}"
        )
    if result.get("state") != "succeeded":
        raise ValidationError(
            f"final AERO speed 0 was not physically confirmed: {result.get('state')!r}"
        )
    return state


def main() -> int:
    args = build_parser().parse_args()
    if not args.confirm_active_output_test:
        print(
            "FAIL: pass --confirm-active-output-test. This validator actively commands "
            "the EC fans to STOP/0 V and AERO to airing OFF / speed 0.",
            file=sys.stderr,
        )
        return 2

    launched: list[tuple[str, ...]] = []
    try:
        core_pid_before = _require_active_pid("ventilation-core.service")
        agent = HostPowerAgent(
            Path("/tmp/wvc-safe-shutdown-validation-unused.sock"),
            core_socket_path=args.core_socket,
            action_delay_seconds=0.0,
            command_launcher=launched.append,
        )

        initial = agent._request_core({"command": "status"})
        if initial.get("ok") is not True:
            raise ValidationError(f"initial core status failed: {initial.get('error')!r}")
        initial_state = _require_object(initial.get("state"), "initial state")
        aero = _require_object(initial_state.get("aero_bus"), "initial aero_bus")
        if aero.get("ready") is not True or aero.get("worker_alive") is not True:
            raise ValidationError("initial AERO worker is not ready/alive")
        if aero.get("online") is not True or aero.get("usable") is not True:
            raise ValidationError("initial AERO is not online+usable")

        # This is the exact PR #77 pre-poweroff path.  Calling the preparation
        # method directly deliberately omits _execute_action(), so the CM5 stays on.
        agent._prepare_peripherals_for_poweroff()

        if launched:
            raise ValidationError(f"host power command unexpectedly launched: {launched!r}")

        final = agent._request_core({"command": "status"})
        final_state = _require_final_safe_state(final)
        core_pid_after = _require_active_pid("ventilation-core.service")
        if core_pid_after != core_pid_before:
            raise ValidationError(
                f"ventilation-core PID changed during validation: {core_pid_before} -> {core_pid_after}"
            )

        result = {
            "ok": True,
            "validation": "safe_shutdown_peripherals_cm5",
            "host_power_executed": False,
            "core_pid_stable": True,
            "fan_mode": final_state.get("mode"),
            "supply_voltage": final_state.get("setpoints", {}).get("supply_voltage"),
            "extract_voltage": final_state.get("setpoints", {}).get("extract_voltage"),
            "output_state_known": final_state.get("output_state_known"),
            "aero_last_control_result": final_state.get("aero_bus", {}).get(
                "last_control_result"
            ),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        if launched:
            print(f"FAIL: unexpected host-power launch record: {launched!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
