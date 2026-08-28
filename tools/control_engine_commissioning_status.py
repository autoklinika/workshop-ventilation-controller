#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ventilation_core.domain.tuning_validation import (
    TUNING_GROUP_REQUIREMENTS,
    TuningValidationProfile,
    ValidationLevel,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATION = ROOT / "config" / "control-engine-tuning-validation-v1.json"
DEFAULT_PLAN = ROOT / "config" / "control-engine-commissioning-plan-v1.json"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def build_status(validation_path: Path, plan_path: Path) -> dict[str, Any]:
    validation = TuningValidationProfile.from_dict(load_json(validation_path))
    plan = load_json(plan_path)
    if plan.get("schema_version") != 1:
        raise ValueError("unsupported commissioning plan schema_version")
    if plan.get("environment_required") != "WORKSHOP":
        raise ValueError("commissioning plan must require WORKSHOP environment")
    plan_groups = plan.get("groups")
    if not isinstance(plan_groups, dict):
        raise ValueError("commissioning plan groups must be an object")
    if set(plan_groups) != set(TUNING_GROUP_REQUIREMENTS):
        raise ValueError("commissioning plan groups must match tuning validation groups exactly")

    rows: list[dict[str, Any]] = []
    for name, required in TUNING_GROUP_REQUIREMENTS.items():
        item = plan_groups[name]
        if not isinstance(item, dict):
            raise ValueError(f"commissioning group {name} must be an object")
        target = ValidationLevel.from_name(item.get("target_level"))
        if target != required:
            raise ValueError(
                f"commissioning group {name} target={target.name} expected={required.name}"
            )
        entry = validation.entry(name)
        complete = entry.level >= required
        rows.append(
            {
                "group": name,
                "current_level": entry.level.name,
                "required_level": required.name,
                "complete": complete,
                "evidence": list(entry.evidence),
                "objective": item.get("objective"),
            }
        )

    return {
        "validation_profile": validation.profile,
        "commissioning_profile": plan.get("profile"),
        "environment_required": "WORKSHOP",
        "complete": all(row["complete"] for row in rows),
        "completed_groups": [row["group"] for row in rows if row["complete"]],
        "pending_groups": [row["group"] for row in rows if not row["complete"]],
        "groups": rows,
        "actuation_authority_granted": False,
        "writes_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report Control Engine workshop commissioning evidence; read-only."
    )
    parser.add_argument("--validation-profile", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--commissioning-plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return non-zero if any commissioning group is still below its required evidence level.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        status = build_status(args.validation_profile, args.commissioning_plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(status, indent=None if args.compact else 2, sort_keys=True))
    if args.require_complete and not status["complete"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
