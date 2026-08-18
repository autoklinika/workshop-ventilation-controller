from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ventilation_core.alert_policy import (
    DEFAULT_RUNTIME_POLICY_PATH,
    AlertPolicyError,
    load_alert_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wvc-alertctl",
        description="Validate Workshop Ventilation Controller AlertV2 policy files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate",
        help="Parse and validate an AlertV2 TOML policy without applying it.",
    )
    validate.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_RUNTIME_POLICY_PATH,
        help=f"policy path (default: {DEFAULT_RUNTIME_POLICY_PATH})",
    )
    validate.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable validation result",
    )
    return parser


def _validate(path: Path, *, json_output: bool) -> int:
    try:
        policy = load_alert_policy(path)
    except AlertPolicyError as exc:
        if json_output:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "path": str(path),
                        "errors": list(exc.errors),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"INVALID: {path}", file=sys.stderr)
            for error in exc.errors:
                print(f"- {error}", file=sys.stderr)
        return 2

    result = {
        "ok": True,
        "path": str(path),
        "schema_version": policy.schema_version,
        "policy_version": policy.policy_version,
        "policy_name": policy.policy_name,
        "alerts": policy.alert_count,
        "sha256": policy.sha256,
    }
    if json_output:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "PASS: AlertV2 policy valid "
            f"path={path} schema={policy.schema_version} "
            f"policy={policy.policy_version} alerts={policy.alert_count} "
            f"sha256={policy.sha256}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return _validate(args.path, json_output=args.json)
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
