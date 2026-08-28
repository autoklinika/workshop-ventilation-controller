from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from ventilation_core.ctl import send_request


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "config" / "control-engine-validated-hardware-v1.json"
FIELD = "tacho_failure_confirmation_seconds"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the physically validated TACHO confirmation interval while preserving "
            "every other Control Engine configuration field."
        )
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--confirm-apply", action="store_true")
    return parser


def _request(socket_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    response = send_request(socket_path, request)
    if response.get("ok") is not True:
        raise RuntimeError(f"core rejected {request.get('command')!r}: {response!r}")
    return response


def _load_seconds(path: Path) -> float:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("validated hardware profile schema_version must be 1")
    tuning = payload.get("validated_tuning")
    if not isinstance(tuning, dict) or set(tuning) != {FIELD}:
        raise RuntimeError(f"validated hardware profile must contain only {FIELD!r}")
    raw = tuning.get(FIELD)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise RuntimeError(f"validated {FIELD} must be numeric")
    seconds = float(raw)
    if not math.isfinite(seconds) or seconds <= 0.0:
        raise RuntimeError(f"validated {FIELD} must be finite and positive")
    return seconds


def _control_engine(response: dict[str, Any]) -> dict[str, Any]:
    control = response.get("control_engine")
    if not isinstance(control, dict):
        raise RuntimeError("control-engine response has no control_engine object")
    if control.get("actuation_supported") is not False:
        raise RuntimeError("refusing configuration update: Control Engine claims actuation authority")
    return control


def _extract_config(control: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    revision = control.get("revision")
    config = control.get("config")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise RuntimeError(f"invalid Control Engine revision: {revision!r}")
    if not isinstance(config, dict):
        raise RuntimeError("Control Engine config is unavailable")
    policy = config.get("policy")
    tuning = policy.get("tuning") if isinstance(policy, dict) else None
    if not isinstance(tuning, dict) or FIELD not in tuning:
        raise RuntimeError(f"Control Engine config is missing policy.tuning.{FIELD}")
    return revision, config


def apply(*, socket_path: Path, profile_path: Path, confirm: bool) -> dict[str, Any]:
    seconds = _load_seconds(profile_path)
    current_response = _request(socket_path, {"command": "control-engine"})
    current_control = _control_engine(current_response)
    current_revision, current_config = _extract_config(current_control)

    current_value = current_config["policy"]["tuning"][FIELD]
    if current_value is not None:
        if isinstance(current_value, bool) or not isinstance(current_value, (int, float)):
            raise RuntimeError(f"current {FIELD} has invalid type: {current_value!r}")
        if math.isclose(float(current_value), seconds, rel_tol=0.0, abs_tol=1e-12):
            print(
                f"PASS: {FIELD} already equals validated {seconds:.3f}s; "
                f"revision remains {current_revision}"
            )
            return {
                "changed": False,
                "revision": current_revision,
                "seconds": seconds,
            }
        raise RuntimeError(
            f"refusing to overwrite existing {FIELD}={current_value!r}; "
            f"validated profile requests {seconds!r}"
        )

    if not confirm:
        raise RuntimeError("refusing persistent Control Engine change without --confirm-apply")

    patched = copy.deepcopy(current_config)
    patched["policy"]["tuning"][FIELD] = seconds

    replace_response = _request(
        socket_path,
        {"command": "control-engine-replace", "config": patched},
    )
    replaced = _control_engine(replace_response)
    new_revision, new_config = _extract_config(replaced)
    if new_revision != current_revision + 1:
        raise RuntimeError(
            f"unexpected revision after patch: before={current_revision}, after={new_revision}"
        )
    if replaced.get("dynamics_reset") is not True:
        raise RuntimeError("Control Engine replace did not report dynamics_reset=true")
    if new_config != patched:
        raise RuntimeError("Control Engine normalized/changed fields outside the requested patch")

    verify_response = _request(socket_path, {"command": "control-engine"})
    verified = _control_engine(verify_response)
    verify_revision, verify_config = _extract_config(verified)
    if verify_revision != new_revision or verify_config != patched:
        raise RuntimeError("Control Engine read-back does not match the persisted patched config")

    print(
        f"PASS: persisted {FIELD}={seconds:.3f}s; revision "
        f"{current_revision} -> {new_revision}; all other config fields preserved"
    )
    return {
        "changed": True,
        "revision_before": current_revision,
        "revision_after": new_revision,
        "seconds": seconds,
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = apply(
            socket_path=args.socket,
            profile_path=args.profile,
            confirm=args.confirm_apply,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
