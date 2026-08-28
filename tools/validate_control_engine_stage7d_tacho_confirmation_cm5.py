from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from tools.validate_control_engine_stage7a_tacho_spinup_cm5 import (
    DEFAULT_SOCKET,
    _request,
    _require_commanded_voltage,
    _state,
    _stop_and_verify,
    inspect_channel,
    require_initial_safe_state,
)


DEFAULT_TEST_VOLTAGE = 1.0
DEFAULT_CONFIRMATION_SECONDS = 4.0
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_POLL_SECONDS = 0.10
DEFAULT_STOP_TIMEOUT_SECONDS = 10.0
DEFAULT_STABLE_SECONDS = 2.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Physical CM5 Stage7D validation of the configured TACHO confirmation interval. "
            "Commands both local EC fans to 1.0 V and verifies CONFIRMING -> HEALTHY without "
            "a false confirmed TACHO fault."
        )
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--confirm-fan-spin-test", action="store_true")
    parser.add_argument("--test-voltage", type=float, default=DEFAULT_TEST_VOLTAGE)
    parser.add_argument("--confirmation-seconds", type=float, default=DEFAULT_CONFIRMATION_SECONDS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--stop-timeout", type=float, default=DEFAULT_STOP_TIMEOUT_SECONDS)
    parser.add_argument("--stable-seconds", type=float, default=DEFAULT_STABLE_SECONDS)
    return parser


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _zone1(state: dict) -> dict:
    shadow = state.get("shadow_automation") or {}
    if shadow.get("actuation_supported") is not False:
        raise RuntimeError("Control Engine unexpectedly has actuation authority")
    zones = [row for row in shadow.get("zones") or [] if isinstance(row, dict)]
    zone = next((row for row in zones if row.get("zone") == "zone-1"), None)
    if zone is None:
        raise RuntimeError("zone-1 SHADOW telemetry is unavailable")
    if zone.get("proposed_supply_voltage") is not None or zone.get("proposed_extract_voltage") is not None:
        raise RuntimeError("Control Engine SHADOW exposed a physical voltage proposal")
    return zone


def _require_configured_confirmation(socket_path: Path, expected: float) -> int:
    response = _request(socket_path, {"command": "control-engine"})
    control = response.get("control_engine") or {}
    if control.get("actuation_supported") is not False:
        raise RuntimeError("Control Engine config unexpectedly supports actuation")
    revision = control.get("revision")
    config = control.get("config") or {}
    policy = config.get("policy") or {}
    tuning = policy.get("tuning") or {}
    actual = _finite(tuning.get("tacho_failure_confirmation_seconds"))
    if actual is None or not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(
            f"configured tacho_failure_confirmation_seconds={actual!r}, expected {expected!r}"
        )
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise RuntimeError(f"invalid Control Engine revision: {revision!r}")
    return revision


def run(args: argparse.Namespace) -> int:
    if not args.confirm_fan_spin_test:
        raise RuntimeError("refusing physical Stage7D fan spin without --confirm-fan-spin-test")
    if not math.isclose(args.test_voltage, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("Stage7D is pinned to the physically characterized 1.0 V worst-case point")
    if not math.isclose(args.confirmation_seconds, 4.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("Stage7D is pinned to the validated 4.0 s confirmation candidate")
    if args.timeout <= args.confirmation_seconds:
        raise RuntimeError("timeout must exceed confirmation interval")
    if args.poll <= 0.0 or args.stop_timeout <= 0.0 or args.stable_seconds <= 0.0:
        raise RuntimeError("poll/stop-timeout/stable-seconds must be positive")

    require_initial_safe_state(_state(args.socket))
    revision = _require_configured_confirmation(args.socket, args.confirmation_seconds)
    print(
        f"PASS: initial STOP / 0 V; Control Engine revision={revision}; "
        f"TACHO confirmation={args.confirmation_seconds:.1f}s; SHADOW non-actuating"
    )

    started = time.monotonic()
    first_healthy: dict[str, float | None] = {"supply": None, "extract": None}
    confirming_seen: dict[str, bool] = {"supply": False, "extract": False}
    healthy_since: float | None = None
    max_prehealthy_elapsed = 0.0

    try:
        _request(
            args.socket,
            {
                "command": "set",
                "supply_voltage": float(args.test_voltage),
                "extract_voltage": float(args.test_voltage),
            },
        )
        print("INFO: commanded both local EC fans to 1.0 V for Stage7D confirmation validation")
        deadline = started + args.timeout

        while time.monotonic() <= deadline:
            state = _state(args.socket)
            _require_commanded_voltage(state, args.test_voltage)
            zone = _zone1(state)
            elapsed = time.monotonic() - started
            samples = {
                channel: inspect_channel(state, channel)
                for channel in ("supply", "extract")
            }

            all_healthy = True
            for channel, sample in samples.items():
                status = sample.shadow_status
                if sample.fault_confirmed is True or status == "FEEDBACK_MISSING_CONFIRMED":
                    raise RuntimeError(
                        f"FALSE TACHO FAULT: {channel} confirmed at {elapsed:.3f}s "
                        f"before healthy feedback; status={status!r}"
                    )
                if status in {"MONITOR_UNAVAILABLE", "CHANNEL_UNAVAILABLE", "CONFIRMATION_TUNING_REQUIRED"}:
                    raise RuntimeError(
                        f"unexpected {channel} supervision status at {elapsed:.3f}s: {status!r}"
                    )

                if sample.healthy:
                    if first_healthy[channel] is None:
                        first_healthy[channel] = elapsed
                        print(
                            f"MEASURED: {channel} CONFIRMING -> HEALTHY at {elapsed:.3f}s, "
                            f"RPM={sample.rpm:.1f}"
                        )
                else:
                    all_healthy = False
                    max_prehealthy_elapsed = max(max_prehealthy_elapsed, elapsed)
                    if sample.feedback_required is not True:
                        raise RuntimeError(f"{channel} feedback not required at physical 1.0 V")
                    if status != "CONFIRMING":
                        raise RuntimeError(
                            f"{channel} pre-feedback status={status!r}, expected CONFIRMING"
                        )
                    confirming_seen[channel] = True

                pattern = zone.get("tacho_fault_pattern")
                if pattern is not None:
                    raise RuntimeError(f"unexpected TACHO fault pattern during healthy start: {pattern!r}")
                if zone.get("tacho_fallback_applied") is True:
                    raise RuntimeError("TACHO fallback applied during healthy physical start")

            if all_healthy:
                if healthy_since is None:
                    healthy_since = time.monotonic()
                if time.monotonic() - healthy_since >= args.stable_seconds:
                    break
            else:
                healthy_since = None
            time.sleep(args.poll)
        else:
            raise RuntimeError(f"both TACHO channels did not become stably HEALTHY within {args.timeout:.1f}s")

        if not all(confirming_seen.values()):
            raise RuntimeError(f"CONFIRMING state was not observed on both channels: {confirming_seen!r}")
        if any(value is None for value in first_healthy.values()):
            raise RuntimeError(f"missing first HEALTHY measurement: {first_healthy!r}")
        if any(float(value) >= args.confirmation_seconds for value in first_healthy.values() if value is not None):
            raise RuntimeError(
                f"healthy feedback arrived at/after configured confirmation deadline: {first_healthy!r}"
            )

        summary = {
            "test_voltage": args.test_voltage,
            "configured_confirmation_seconds": args.confirmation_seconds,
            "control_engine_revision": revision,
            "confirming_seen": confirming_seen,
            "first_healthy_seconds": first_healthy,
            "max_prehealthy_elapsed_seconds": max_prehealthy_elapsed,
            "stable_healthy_seconds": args.stable_seconds,
            "false_fault_seen": False,
            "fallback_applied": False,
        }
        print("===== STAGE7D TACHO CONFIRMATION VALIDATION =====")
        print(json.dumps(summary, indent=2, sort_keys=True))
        print("PASS: 4.0 s confirmation candidate did not false-trip at physical 1.0 V")
        return 0
    finally:
        _stop_and_verify(args.socket, timeout=args.stop_timeout, poll=args.poll)


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
