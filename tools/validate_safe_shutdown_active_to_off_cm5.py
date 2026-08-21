#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from ventilation_core.host_power_agent import DEFAULT_CORE_SOCKET, HostPowerAgent


class ValidationError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Physically validate PR #77 from a real running state to the complete "
            "peripheral-off state, without executing host poweroff"
        )
    )
    parser.add_argument(
        "--confirm-active-to-off-test",
        action="store_true",
        help=(
            "Required acknowledgement that both EC fans will be commanded to 3.0 V, "
            "AERO speed will be set to 1 and airing enabled before validating the exact "
            "PR #77 shutdown-preparation path back to STOP/0 V/AERO 0"
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


def _require_ok(response: dict[str, Any], label: str) -> dict[str, Any]:
    if response.get("ok") is not True:
        raise ValidationError(f"{label} failed: {response.get('error') or response!r}")
    return response


def _require_aero_result(
    response: dict[str, Any], *, kind: str, target: int, label: str
) -> dict[str, Any]:
    _require_ok(response, label)
    result = _require_object(response.get("aero_control"), f"{label}.aero_control")
    if result.get("kind") != kind:
        raise ValidationError(f"{label} returned kind={result.get('kind')!r}")
    if result.get("target_value") != target:
        raise ValidationError(f"{label} target={result.get('target_value')!r}, expected {target}")
    if result.get("state") != "succeeded":
        raise ValidationError(f"{label} was not confirmed: state={result.get('state')!r}")
    if result.get("physical_confirmation") is not True:
        raise ValidationError(f"{label} lacks physical confirmation: {result!r}")
    return result


def _status(agent: HostPowerAgent) -> dict[str, Any]:
    return _require_ok(agent._request_core({"command": "status"}), "core status")


def _fan_tacho(state: dict[str, Any], channel: str) -> dict[str, Any]:
    tacho = _require_object(state.get("tacho"), "tacho")
    if tacho.get("ready") is not True or tacho.get("worker_alive") is not True:
        raise ValidationError("TACHO monitor is not ready/alive")
    return _require_object(tacho.get(channel), f"tacho.{channel}")


def _wait_running_tacho(agent: HostPowerAgent, timeout_seconds: float = 12.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        state = _require_object(_status(agent).get("state"), "state")
        supply = _fan_tacho(state, "supply")
        extract = _fan_tacho(state, "extract")
        last = {"supply": supply, "extract": extract}
        if (
            supply.get("valid") is True
            and extract.get("valid") is True
            and float(supply.get("rpm") or 0.0) > 100.0
            and float(extract.get("rpm") or 0.0) > 100.0
        ):
            return last
        time.sleep(0.25)
    raise ValidationError(f"both EC fans did not reach confirmed running TACHO state: {last!r}")


def _wait_stopped_tacho(agent: HostPowerAgent, timeout_seconds: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        state = _require_object(_status(agent).get("state"), "state")
        supply = _fan_tacho(state, "supply")
        extract = _fan_tacho(state, "extract")
        last = {"supply": supply, "extract": extract}
        if (
            supply.get("valid") is False
            and extract.get("valid") is False
            and float(supply.get("rpm") or 0.0) == 0.0
            and float(extract.get("rpm") or 0.0) == 0.0
        ):
            return last
        time.sleep(0.25)
    raise ValidationError(f"both EC fan TACHO channels did not confirm stop: {last!r}")


def _require_final_safe_state(status: dict[str, Any]) -> dict[str, Any]:
    state = _require_object(_require_ok(status, "final core status").get("state"), "state")
    if state.get("mode") != "STOP":
        raise ValidationError(f"final mode is not STOP: {state.get('mode')!r}")
    setpoints = _require_object(state.get("setpoints"), "setpoints")
    if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
        raise ValidationError(f"final EC outputs are not 0 V: {setpoints!r}")
    if state.get("output_state_known") is not True:
        raise ValidationError("final EC output state is not confirmed")

    aero = _require_object(state.get("aero_bus"), "aero_bus")
    if aero.get("ready") is not True or aero.get("worker_alive") is not True:
        raise ValidationError("AERO worker is not ready/alive after shutdown preparation")
    if aero.get("online") is not True or aero.get("usable") is not True:
        raise ValidationError("AERO is not online+usable after shutdown preparation")
    result = _require_object(aero.get("last_control_result"), "aero_bus.last_control_result")
    if result.get("kind") != "speed" or result.get("target_value") != 0:
        raise ValidationError(f"final AERO command is not speed 0: {result!r}")
    if result.get("state") != "succeeded" or result.get("physical_confirmation") is not True:
        raise ValidationError(f"final AERO speed 0 is not physically confirmed: {result!r}")
    observed = _require_object(result.get("observed_power"), "aero observed_power")
    if observed.get("fan_1_percent") != 0 or observed.get("fan_2_percent") != 0:
        raise ValidationError(f"AERO fan power is not 0% after shutdown preparation: {observed!r}")
    return state


def _precondition_aero_off(agent: HostPowerAgent) -> None:
    """Put AERO in a deterministic 0/off state before building the active test state."""
    _require_aero_result(
        agent._request_core({"command": "aero-airing", "enabled": False}),
        kind="airing",
        target=0,
        label="AERO precondition airing OFF",
    )
    _require_aero_result(
        agent._request_core({"command": "aero-speed", "speed": 0}),
        kind="speed",
        target=0,
        label="AERO precondition speed 0",
    )


def _best_effort_off(agent: HostPowerAgent) -> None:
    # Use the same safe ordering as production shutdown.  Each request is isolated
    # so a failure of one cleanup step cannot prevent the remaining attempts.
    for payload in (
        {"command": "stop"},
        {"command": "aero-airing", "enabled": False},
        {"command": "aero-speed", "speed": 0},
    ):
        try:
            agent._request_core(payload)
        except Exception:
            pass


def main() -> int:
    args = build_parser().parse_args()
    if not args.confirm_active_to_off_test:
        print(
            "FAIL: pass --confirm-active-to-off-test. This validator deliberately runs "
            "the EC fans at 3.0 V and AERO at speed 1 / airing ON before stopping them.",
            file=sys.stderr,
        )
        return 2

    launched: list[tuple[str, ...]] = []
    agent: HostPowerAgent | None = None
    try:
        core_pid_before = _require_active_pid("ventilation-core.service")
        agent = HostPowerAgent(
            Path("/tmp/wvc-safe-shutdown-active-validation-unused.sock"),
            core_socket_path=args.core_socket,
            action_delay_seconds=0.0,
            command_launcher=launched.append,
        )

        initial_state = _require_object(_status(agent).get("state"), "initial state")
        aero = _require_object(initial_state.get("aero_bus"), "initial aero_bus")
        if aero.get("ready") is not True or aero.get("worker_alive") is not True:
            raise ValidationError("initial AERO worker is not ready/alive")
        if aero.get("online") is not True or aero.get("usable") is not True:
            raise ValidationError("initial AERO is not online+usable")

        print("INFO: preconditioning AERO to airing OFF / speed 0")
        _precondition_aero_off(agent)

        print("INFO: commanding both EC fans to 3.0 V")
        running = _require_ok(
            agent._request_core(
                {"command": "set", "supply_voltage": 3.0, "extract_voltage": 3.0}
            ),
            "EC fan active setpoint",
        )
        running_state = _require_object(running.get("state"), "running state")
        if running_state.get("mode") != "MANUAL":
            raise ValidationError(f"EC fan active command did not enter MANUAL: {running_state!r}")

        # IMPORTANT: set speed before enabling airing.  Airing forces the AERO fans
        # to 100%, so doing it first can mask the physical power change required to
        # confirm a speed-register write and would create a false 60 s timeout.
        print("INFO: setting AERO speed 1 while airing is OFF")
        aero_speed_active = _require_aero_result(
            agent._request_core({"command": "aero-speed", "speed": 1}),
            kind="speed",
            target=1,
            label="AERO speed 1",
        )
        print("INFO: enabling AERO airing after speed 1 is confirmed")
        aero_airing_active = _require_aero_result(
            agent._request_core({"command": "aero-airing", "enabled": True}),
            kind="airing",
            target=1,
            label="AERO airing ON",
        )

        active_tacho = _wait_running_tacho(agent)
        print(
            "INFO: EC fans confirmed running: "
            f"supply={active_tacho['supply'].get('rpm'):.1f} rpm "
            f"extract={active_tacho['extract'].get('rpm'):.1f} rpm"
        )

        # Exact PR #77 pre-poweroff sequence.  _execute_action() is never called,
        # therefore this test cannot shut down or reboot the host.
        print("INFO: executing exact PR #77 pre-poweroff peripheral sequence")
        agent._prepare_peripherals_for_poweroff()

        if launched:
            raise ValidationError(f"host power command unexpectedly launched: {launched!r}")

        stopped_tacho = _wait_stopped_tacho(agent)
        final_state = _require_final_safe_state(_status(agent))
        core_pid_after = _require_active_pid("ventilation-core.service")
        if core_pid_after != core_pid_before:
            raise ValidationError(
                f"ventilation-core PID changed during validation: {core_pid_before} -> {core_pid_after}"
            )

        result = {
            "ok": True,
            "validation": "safe_shutdown_active_to_off_cm5",
            "host_power_executed": False,
            "core_pid_stable": True,
            "active": {
                "ec_setpoint_v": 3.0,
                "supply_rpm": active_tacho["supply"].get("rpm"),
                "extract_rpm": active_tacho["extract"].get("rpm"),
                "aero_speed_result": aero_speed_active,
                "aero_airing_result": aero_airing_active,
            },
            "final": {
                "mode": final_state.get("mode"),
                "supply_voltage": final_state.get("setpoints", {}).get("supply_voltage"),
                "extract_voltage": final_state.get("setpoints", {}).get("extract_voltage"),
                "output_state_known": final_state.get("output_state_known"),
                "supply_tacho": stopped_tacho["supply"],
                "extract_tacho": stopped_tacho["extract"],
                "aero_last_control_result": final_state.get("aero_bus", {}).get(
                    "last_control_result"
                ),
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        print("PASS: real ACTIVE -> OFF shutdown preparation validated without host poweroff")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if agent is not None:
            _best_effort_off(agent)
        if launched:
            print(f"FAIL: unexpected host-power launch record: {launched!r}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
