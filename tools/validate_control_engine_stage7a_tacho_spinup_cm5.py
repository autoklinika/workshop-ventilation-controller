from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ventilation_core.ctl import send_request


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_TEST_VOLTAGE = 2.0
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_STOP_TIMEOUT_SECONDS = 10.0
DEFAULT_POLL_SECONDS = 0.10
DEFAULT_STABLE_SAMPLES = 10


@dataclass(frozen=True)
class ChannelSample:
    channel: str
    raw_valid: bool
    rpm: float | None
    shadow_status: str | None
    feedback_required: bool | None
    fault_confirmed: bool | None

    @property
    def healthy(self) -> bool:
        return (
            self.raw_valid
            and self.rpm is not None
            and self.rpm > 0.0
            and self.shadow_status == "HEALTHY"
            and self.feedback_required is True
            and self.fault_confirmed is False
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Physical CM5 validator for Control Engine Stage7A TACHO spin-up. "
            "This intentionally commands local EC fans and always returns them to STOP / 0 V."
        )
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--confirm-fan-spin-test", action="store_true")
    parser.add_argument("--test-voltage", type=float, default=DEFAULT_TEST_VOLTAGE)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--stop-timeout", type=float, default=DEFAULT_STOP_TIMEOUT_SECONDS)
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--stable-samples", type=int, default=DEFAULT_STABLE_SAMPLES)
    return parser


def _request(socket_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    response = send_request(socket_path, request)
    if response.get("ok") is not True:
        raise RuntimeError(f"core rejected request {request.get('command')!r}: {response!r}")
    return response


def _state(socket_path: Path) -> dict[str, Any]:
    response = _request(socket_path, {"command": "status"})
    state = response.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("core status response has no state object")
    return state


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _zone1_shadow(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    shadow = state.get("shadow_automation") or {}
    if not isinstance(shadow, dict):
        raise RuntimeError("shadow_automation is unavailable")
    if shadow.get("actuation_supported") is not False:
        raise RuntimeError("Control Engine unexpectedly has actuation authority")
    zones = [row for row in shadow.get("zones") or [] if isinstance(row, dict)]
    zone1 = next((row for row in zones if row.get("zone") == "zone-1"), None)
    if zone1 is None:
        raise RuntimeError("zone-1 SHADOW telemetry is unavailable")
    if zone1.get("proposed_supply_voltage") is not None:
        raise RuntimeError("SHADOW exposed proposed_supply_voltage")
    if zone1.get("proposed_extract_voltage") is not None:
        raise RuntimeError("SHADOW exposed proposed_extract_voltage")
    return shadow, zone1


def inspect_channel(state: dict[str, Any], channel: str) -> ChannelSample:
    if channel not in {"supply", "extract"}:
        raise ValueError(f"unsupported channel: {channel}")
    tacho = state.get("tacho") or {}
    raw = tacho.get(channel) or {}
    _, zone1 = _zone1_shadow(state)
    rpm = _finite_float(raw.get("rpm"))
    return ChannelSample(
        channel=channel,
        raw_valid=raw.get("valid") is True,
        rpm=rpm,
        shadow_status=zone1.get(f"tacho_{channel}_status"),
        feedback_required=zone1.get(f"tacho_{channel}_feedback_required"),
        fault_confirmed=zone1.get(f"tacho_{channel}_fault_confirmed"),
    )


def require_initial_safe_state(state: dict[str, Any]) -> None:
    if state.get("hardware_ready") is not True:
        raise RuntimeError("hardware_ready is not true")
    if state.get("output_state_known") is not True:
        raise RuntimeError("output_state_known is not true")
    if state.get("mode") != "STOP":
        raise RuntimeError(f"initial mode is not STOP: {state.get('mode')!r}")
    setpoints = state.get("setpoints") or {}
    if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
        raise RuntimeError(f"initial EC setpoints are not 0 V: {setpoints!r}")

    tacho = state.get("tacho") or {}
    if tacho.get("ready") is not True or tacho.get("worker_alive") is not True:
        raise RuntimeError("TACHO monitor is not ready/alive")
    for channel in ("supply", "extract"):
        raw = tacho.get(channel)
        if not isinstance(raw, dict):
            raise RuntimeError(f"TACHO channel {channel} is unavailable")
        rpm = _finite_float(raw.get("rpm"))
        if rpm is not None and rpm > 0.0:
            raise RuntimeError(f"initial {channel} TACHO still reports motion: {rpm:.1f} RPM")

    _, zone1 = _zone1_shadow(state)
    for channel in ("supply", "extract"):
        if zone1.get(f"tacho_{channel}_feedback_required") is not False:
            raise RuntimeError(f"{channel} TACHO unexpectedly required at 0 V")
        if zone1.get(f"tacho_{channel}_status") != "NOT_REQUIRED":
            raise RuntimeError(
                f"{channel} TACHO initial status={zone1.get(f'tacho_{channel}_status')!r}, expected NOT_REQUIRED"
            )
        if zone1.get(f"tacho_{channel}_fault_confirmed") is not False:
            raise RuntimeError(f"{channel} TACHO fault is confirmed at 0 V")


def _require_commanded_voltage(state: dict[str, Any], voltage: float) -> None:
    setpoints = state.get("setpoints") or {}
    if setpoints.get("supply_voltage") != voltage or setpoints.get("extract_voltage") != voltage:
        raise RuntimeError(f"physical setpoint state changed unexpectedly: {setpoints!r}")
    _zone1_shadow(state)


def _stop_and_verify(socket_path: Path, *, timeout: float, poll: float) -> None:
    _request(socket_path, {"command": "stop"})
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        last = _state(socket_path)
        setpoints = last.get("setpoints") or {}
        supply = inspect_channel(last, "supply")
        extract = inspect_channel(last, "extract")
        zero = setpoints.get("supply_voltage") == 0.0 and setpoints.get("extract_voltage") == 0.0
        stopped = (
            (supply.rpm is None or supply.rpm == 0.0)
            and (extract.rpm is None or extract.rpm == 0.0)
        )
        _, zone1 = _zone1_shadow(last)
        not_required = all(
            zone1.get(f"tacho_{channel}_feedback_required") is False
            and zone1.get(f"tacho_{channel}_status") == "NOT_REQUIRED"
            and zone1.get(f"tacho_{channel}_fault_confirmed") is False
            for channel in ("supply", "extract")
        )
        if zero and stopped and not_required:
            print("PASS: cleanup STOP / 0 V / no observed local fan motion / TACHO NOT_REQUIRED")
            return
        time.sleep(poll)
    raise RuntimeError(f"STOP cleanup did not settle within {timeout:.1f}s; last_state={last!r}")


def run(args: argparse.Namespace) -> int:
    if not args.confirm_fan_spin_test:
        raise RuntimeError("refusing physical fan spin test without --confirm-fan-spin-test")
    if not (1.0 <= args.test_voltage <= 3.0):
        raise RuntimeError("Stage7A test voltage must stay within guarded low-speed range 1.0..3.0 V")
    if args.timeout <= 0.0 or args.stop_timeout <= 0.0 or args.poll <= 0.0:
        raise RuntimeError("timeouts and poll interval must be positive")
    if args.stable_samples < 1:
        raise RuntimeError("stable-samples must be >= 1")

    initial = _state(args.socket)
    require_initial_safe_state(initial)
    print("PASS: initial STOP / 0 V / TACHO monitor ready / SHADOW non-actuating")

    command_started = time.monotonic()
    first_healthy: dict[str, float | None] = {"supply": None, "extract": None}
    rpm_min: dict[str, float | None] = {"supply": None, "extract": None}
    rpm_max: dict[str, float | None] = {"supply": None, "extract": None}
    stable_count = 0
    reached_stable = False

    try:
        _request(
            args.socket,
            {
                "command": "set",
                "supply_voltage": float(args.test_voltage),
                "extract_voltage": float(args.test_voltage),
            },
        )
        print(f"INFO: commanded physical EC fans to {args.test_voltage:.1f} V for TACHO measurement")
        deadline = command_started + args.timeout

        while time.monotonic() <= deadline:
            state = _state(args.socket)
            _require_commanded_voltage(state, float(args.test_voltage))
            samples = {
                channel: inspect_channel(state, channel)
                for channel in ("supply", "extract")
            }
            elapsed = time.monotonic() - command_started

            for channel, sample in samples.items():
                if sample.rpm is not None and sample.rpm > 0.0:
                    rpm_min[channel] = sample.rpm if rpm_min[channel] is None else min(rpm_min[channel], sample.rpm)
                    rpm_max[channel] = sample.rpm if rpm_max[channel] is None else max(rpm_max[channel], sample.rpm)
                if sample.healthy and first_healthy[channel] is None:
                    first_healthy[channel] = elapsed
                    print(
                        f"MEASURED: {channel} first HEALTHY at {elapsed:.3f}s, "
                        f"RPM={sample.rpm:.1f}"
                    )

            if all(sample.healthy for sample in samples.values()):
                stable_count += 1
            else:
                stable_count = 0

            if stable_count >= args.stable_samples:
                reached_stable = True
                print(
                    f"PASS: both TACHO channels HEALTHY for {args.stable_samples} consecutive samples"
                )
                break
            time.sleep(args.poll)

        if not reached_stable:
            final_state = _state(args.socket)
            final_samples = {
                channel: inspect_channel(final_state, channel).__dict__
                for channel in ("supply", "extract")
            }
            raise RuntimeError(
                f"both TACHO channels did not become stably HEALTHY within {args.timeout:.1f}s: "
                f"{final_samples!r}"
            )

        summary = {
            "test_voltage": float(args.test_voltage),
            "first_healthy_seconds": first_healthy,
            "observed_rpm_min": rpm_min,
            "observed_rpm_max": rpm_max,
            "stable_samples": args.stable_samples,
            "poll_seconds": args.poll,
        }
        print("===== STAGE7A MEASUREMENT =====")
        print(json.dumps(summary, indent=2, sort_keys=True))
        print("NOTE: measurement only; no Control Engine tuning value was written automatically")
        return 0
    finally:
        _stop_and_verify(args.socket, timeout=args.stop_timeout, poll=args.poll)


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except Exception as exc:  # validator boundary: always print one concise failure
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
