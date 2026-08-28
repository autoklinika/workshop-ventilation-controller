#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ventilation_core.domain.commissioning_candidate import CommissioningCandidate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "config" / "control-engine-commissioning-candidate-template-v1.json"


def validate(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate = CommissioningCandidate.from_dict(payload)
    blockers = candidate.blockers()
    return {
        "candidate_id": candidate.candidate_id,
        "environment": candidate.environment,
        "source_config_revision": candidate.source_config_revision,
        "complete_for_review": candidate.complete_for_review,
        "blockers": list(blockers),
        "completed_groups": [
            name
            for name, group in candidate.groups
            if group.values_complete
            and not any(blocker.startswith(f"CANDIDATE_{name.upper()}_") for blocker in blockers)
        ],
        "pending_groups": [
            name
            for name, _ in candidate.groups
            if any(blocker.startswith(f"CANDIDATE_{name.upper()}_") for blocker in blockers)
        ],
        "actuation_authority_granted": False,
        "writes_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a Control Engine workshop commissioning candidate; read-only."
    )
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return non-zero until every tuning group has values and required evidence level.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(args.candidate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=None if args.compact else 2, sort_keys=True))
    if args.require_complete and not result["complete_for_review"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
