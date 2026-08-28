#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ventilation_core.application.control_engine_scenario import ControlEngineScenarioRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay a deterministic synthetic Control Engine SHADOW scenario."
    )
    parser.add_argument("scenario", type=Path, help="Path to scenario JSON")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON instead of pretty formatted output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with args.scenario.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        result = ControlEngineScenarioRunner().run(payload).to_dict()
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"CONTROL_ENGINE_SCENARIO_FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.compact:
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
