#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Callable

from ventilation_core.ctl import send_request


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def capture_session(
    *,
    socket_path: Path,
    output: Path,
    session_id: str,
    samples: int,
    interval_seconds: float,
    requester: Callable[[Path, dict[str, object]], dict[str, object]] = send_request,
    clock: Callable[[], datetime] = utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    if not session_id.strip() or len(session_id) > 120:
        raise ValueError("session_id must be non-empty text up to 120 characters")
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if interval_seconds <= 0.0:
        raise ValueError("interval_seconds must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)

    header = {
        "record_type": "session",
        "schema_version": 1,
        "session_id": session_id,
        "environment": "WORKSHOP",
        "source": "ventilation-core:status",
        "started_at_utc": clock().isoformat(),
        "requested_samples": samples,
        "interval_seconds": interval_seconds,
        "actuation_authority_granted": False,
        "core_writes_performed": False,
    }

    captured = 0
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(header, separators=(",", ":"), sort_keys=True) + "\n")
        stream.flush()
        for sequence in range(samples):
            response = requester(socket_path, {"command": "status"})
            if response.get("ok") is not True or not isinstance(response.get("state"), dict):
                raise RuntimeError(f"authoritative status request failed: {response!r}")
            state = response["state"]
            shadow = state.get("shadow_automation") or {}
            if shadow.get("actuation_supported") is not False:
                raise RuntimeError("commissioning capture requires SHADOW-only Control Engine")
            record = {
                "record_type": "sample",
                "schema_version": 1,
                "session_id": session_id,
                "sequence": sequence,
                "captured_at_utc": clock().isoformat(),
                "state": state,
            }
            stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
            stream.flush()
            captured += 1
            if sequence + 1 < samples:
                sleeper(interval_seconds)

    return {
        "session_id": session_id,
        "environment": "WORKSHOP",
        "output": str(output),
        "captured_samples": captured,
        "interval_seconds": interval_seconds,
        "actuation_authority_granted": False,
        "core_writes_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture authoritative WVC telemetry for real-workshop commissioning; status-only."
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--samples", type=int, default=3600)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--confirm-workshop-commissioning",
        choices=("YES",),
        required=True,
        help="Required acknowledgement that the capture is from the representative final workshop, not LAB.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = capture_session(
            socket_path=args.socket,
            output=args.output,
            session_id=args.session_id,
            samples=args.samples,
            interval_seconds=args.interval,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
