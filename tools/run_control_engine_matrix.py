#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from ventilation_core.application.control_engine_matrix import ControlEngineMatrixRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an independent Cartesian Control Engine SHADOW matrix."
    )
    parser.add_argument("matrix", type=Path, help="Path to matrix JSON")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON instead of pretty formatted output",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit a bounded summary instead of all matrix cases",
    )
    return parser


def summarize(payload: dict) -> dict:
    status_counts: Counter[str] = Counter()
    zone1_state_counts: Counter[str] = Counter()
    zone2_state_counts: Counter[str] = Counter()
    safety_cases = 0
    fallback_cases = 0

    for case in payload.get("cases") or []:
        shadow = case.get("shadow") or {}
        status_counts[str(shadow.get("status"))] += 1
        zones = {
            row.get("sensor_address"): row
            for row in shadow.get("zones") or []
            if isinstance(row, dict)
        }
        zone1 = zones.get(1) or {}
        zone2 = zones.get(2) or {}
        zone1_state_counts[str(zone1.get("automation_state"))] += 1
        zone2_state_counts[str(zone2.get("automation_state"))] += 1
        if any(bool(row.get("safety_override")) for row in zones.values()):
            safety_cases += 1
        if any(bool(row.get("sensor_fallback_applied")) for row in zones.values()):
            fallback_cases += 1

    return {
        "schema_version": payload.get("schema_version"),
        "name": payload.get("name"),
        "policy_version": payload.get("policy_version"),
        "actuation_supported": payload.get("actuation_supported"),
        "dimensions": payload.get("dimensions"),
        "case_count": payload.get("case_count"),
        "status_counts": dict(sorted(status_counts.items())),
        "zone1_automation_state_counts": dict(sorted(zone1_state_counts.items())),
        "zone2_automation_state_counts": dict(sorted(zone2_state_counts.items())),
        "safety_blocked_cases": safety_cases,
        "sensor_fallback_cases": fallback_cases,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with args.matrix.open("r", encoding="utf-8") as handle:
            matrix = json.load(handle)
        result = ControlEngineMatrixRunner().run(matrix).to_dict()
        if args.summary:
            result = summarize(result)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"CONTROL_ENGINE_MATRIX_FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.compact:
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
