from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import deque
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


DEFAULT_TEST_VOLTAGE = 2.0
DEFAULT_HOLD_SECONDS = 15.0
DEFAULT_CYCLES = 3
DEFAULT_POLL_SECONDS = 0.10
DEFAULT_STOP_TIMEOUT_SECONDS = 10.0
DEFAULT_REST_SECONDS = 2.0
DEFAULT_REPORT_EVERY_SECONDS = 1.0
DEFAULT_TAIL_WINDOW_SECONDS = 5.0
DEFAULT_HEALTH_TAIL_SAMPLES = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Physical CM5 Stage7B TACHO characterization. Commands both local EC fans "
            "to a guarded low voltage for a fixed hold time, records the whole RPM ramp, "
            "then always returns to STOP / 0 V."
        )
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--confirm-fan-spin-test", action="store_true")
    parser.add_argument("--test-voltage", type=float, default=DEFAULT_TEST_VOLTAGE)
    parser.add_argument("--hold-seconds", type=float, default=DEFAULT_HOLD_SECONDS)
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--stop-timeout", type=float, default=DEFAULT_STOP_TIMEOUT_SECONDS)
    parser.add_argument("--rest-seconds", type=float, default=DEFAULT_REST_SECONDS)
    parser.add_argument("--report-every", type=float, default=DEFAULT_REPORT_EVERY_SECONDS)
    parser.add_argument("--tail-window", type=float, default=DEFAULT_TAIL_WINDOW_SECONDS)
    return parser


def _finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def _tail_stats(samples: list[tuple[float, float]], *, hold_seconds: float, tail_window: float) -> dict[str, float]:
    cutoff = max(0.0, hold_seconds - tail_window)
    values = [rpm for elapsed, rpm in samples if elapsed >= cutoff and math.isfinite(rpm) and rpm > 0.0]
    if not values:
        raise RuntimeError("no valid RPM samples in final characterization window")
    return {
        "count": float(len(values)),
        "min_rpm": min(values),
        "max_rpm": max(values),
        "mean_rpm": statistics.fmean(values),
        "spread_rpm": max(values) - min(values),
    }


def _run_cycle(args: argparse.Namespace, cycle: int) -> dict[str, object]:
    initial = _state(args.socket)
    require_initial_safe_state(initial)

    started = time.monotonic()
    first_healthy: dict[str, float | None] = {"supply": None, "extract": None}
    rpm_samples: dict[str, list[tuple[float, float]]] = {"supply": [], "extract": []}
    health_tail: deque[bool] = deque(maxlen=DEFAULT_HEALTH_TAIL_SAMPLES)
    next_report = 0.0

    try:
        _request(
            args.socket,
            {
                "command": "set",
                "supply_voltage": float(args.test_voltage),
                "extract_voltage": float(args.test_voltage),
            },
        )
        print(
            f"INFO: cycle {cycle}/{args.cycles}: commanded both local EC fans to "
            f"{args.test_voltage:.1f} V for fixed {args.hold_seconds:.1f}s hold"
        )

        while True:
            state = _state(args.socket)
            _require_commanded_voltage(state, float(args.test_voltage))
            elapsed = time.monotonic() - started
            samples = {
                channel: inspect_channel(state, channel)
                for channel in ("supply", "extract")
            }

            for channel, sample in samples.items():
                if _finite_positive(sample.rpm):
                    assert sample.rpm is not None
                    rpm_samples[channel].append((elapsed, float(sample.rpm)))
                if sample.healthy and first_healthy[channel] is None:
                    first_healthy[channel] = elapsed
                    print(
                        f"MEASURED: cycle {cycle} {channel} first HEALTHY at "
                        f"{elapsed:.3f}s, RPM={sample.rpm:.1f}"
                    )

            health_tail.append(all(sample.healthy for sample in samples.values()))

            if elapsed >= next_report:
                supply_rpm = samples["supply"].rpm
                extract_rpm = samples["extract"].rpm
                print(
                    f"TRACE: cycle {cycle} t={elapsed:5.2f}s "
                    f"supply={0.0 if supply_rpm is None else supply_rpm:7.1f} RPM "
                    f"extract={0.0 if extract_rpm is None else extract_rpm:7.1f} RPM"
                )
                next_report += args.report_every

            if elapsed >= args.hold_seconds:
                break
            time.sleep(args.poll)

        if any(value is None for value in first_healthy.values()):
            raise RuntimeError(
                f"cycle {cycle}: both TACHO channels did not become HEALTHY during fixed hold: "
                f"{first_healthy!r}"
            )
        if len(health_tail) < DEFAULT_HEALTH_TAIL_SAMPLES or not all(health_tail):
            raise RuntimeError(
                f"cycle {cycle}: both TACHO channels were not HEALTHY for the final "
                f"{DEFAULT_HEALTH_TAIL_SAMPLES} samples"
            )

        tail = {
            channel: _tail_stats(
                rpm_samples[channel],
                hold_seconds=float(args.hold_seconds),
                tail_window=float(args.tail_window),
            )
            for channel in ("supply", "extract")
        }
        return {
            "cycle": cycle,
            "first_healthy_seconds": first_healthy,
            "tail_window_seconds": float(args.tail_window),
            "tail_rpm": tail,
            "observed_rpm_min": {
                channel: min(rpm for _, rpm in rpm_samples[channel])
                for channel in ("supply", "extract")
            },
            "observed_rpm_max": {
                channel: max(rpm for _, rpm in rpm_samples[channel])
                for channel in ("supply", "extract")
            },
        }
    finally:
        _stop_and_verify(args.socket, timeout=float(args.stop_timeout), poll=float(args.poll))


def run(args: argparse.Namespace) -> int:
    if not args.confirm_fan_spin_test:
        raise RuntimeError("refusing physical fan spin test without --confirm-fan-spin-test")
    if not (1.0 <= args.test_voltage <= 3.0):
        raise RuntimeError("Stage7B test voltage must stay within guarded low-speed range 1.0..3.0 V")
    if args.hold_seconds < 10.0:
        raise RuntimeError("Stage7B hold-seconds must be >= 10.0 to characterize full spin-up")
    if not (1 <= args.cycles <= 5):
        raise RuntimeError("Stage7B cycles must be within 1..5")
    if args.poll <= 0.0 or args.stop_timeout <= 0.0:
        raise RuntimeError("poll and stop-timeout must be positive")
    if args.rest_seconds < 0.0:
        raise RuntimeError("rest-seconds must be >= 0")
    if args.report_every <= 0.0:
        raise RuntimeError("report-every must be positive")
    if not (1.0 <= args.tail_window < args.hold_seconds):
        raise RuntimeError("tail-window must be >= 1.0 and shorter than hold-seconds")

    require_initial_safe_state(_state(args.socket))
    print("PASS: initial STOP / 0 V / TACHO monitor ready / SHADOW non-actuating")

    results: list[dict[str, object]] = []
    for cycle in range(1, args.cycles + 1):
        result = _run_cycle(args, cycle)
        results.append(result)
        if cycle < args.cycles:
            if args.rest_seconds > 0.0:
                print(f"INFO: cycle {cycle}: stopped; resting {args.rest_seconds:.1f}s before next start")
                time.sleep(args.rest_seconds)
            require_initial_safe_state(_state(args.socket))

    max_first_healthy = {
        channel: max(
            float(result["first_healthy_seconds"][channel])
            for result in results
        )
        for channel in ("supply", "extract")
    }
    tail_means = {
        channel: [
            float(result["tail_rpm"][channel]["mean_rpm"])
            for result in results
        ]
        for channel in ("supply", "extract")
    }
    summary = {
        "test_voltage": float(args.test_voltage),
        "hold_seconds": float(args.hold_seconds),
        "cycles": int(args.cycles),
        "poll_seconds": float(args.poll),
        "rest_seconds": float(args.rest_seconds),
        "tail_window_seconds": float(args.tail_window),
        "max_first_healthy_seconds": max_first_healthy,
        "tail_mean_rpm_across_cycles": {
            channel: {
                "min": min(tail_means[channel]),
                "max": max(tail_means[channel]),
                "mean": statistics.fmean(tail_means[channel]),
            }
            for channel in ("supply", "extract")
        },
        "cycle_results": results,
    }
    print("===== STAGE7B EXTENDED TACHO CHARACTERIZATION =====")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "NOTE: max_first_healthy_seconds is an observed detection bound, not an automatic "
        "production confirmation setting"
    )
    print("NOTE: no Control Engine tuning value was written automatically")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
