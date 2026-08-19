#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import threading
from pathlib import Path

from ventilation_core.alert_v2_stage4b_runtime import (
    DEFAULT_CORE_SOCKET,
    DEFAULT_STAGE4B_SOCKET,
    Stage4BShadowRuntime,
    serve_shadow_runtime,
)
from ventilation_core.service_plane_monitor import DEFAULT_SERVICE_AGENT_SOCKET


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT_DIR / "config" / "alerts-v2.default.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AlertV2 Stage 4B live read-only shadow runtime"
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--core-socket", type=Path, default=DEFAULT_CORE_SOCKET)
    parser.add_argument(
        "--service-agent-socket",
        type=Path,
        default=DEFAULT_SERVICE_AGENT_SOCKET,
    )
    parser.add_argument("--listen-socket", type=Path, default=DEFAULT_STAGE4B_SOCKET)
    parser.add_argument("--refresh-interval", type=float, default=0.5)
    parser.add_argument("--core-timeout", type=float, default=0.5)
    parser.add_argument("--service-timeout", type=float, default=0.35)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    runtime = Stage4BShadowRuntime(
        policy_path=args.policy,
        core_socket=args.core_socket,
        service_agent_socket=args.service_agent_socket,
        core_timeout_seconds=args.core_timeout,
        service_timeout_seconds=args.service_timeout,
    )
    print(
        "AlertV2 Stage 4B shadow runtime starting: "
        f"listen={args.listen_socket} core={args.core_socket} "
        f"service={args.service_agent_socket} policy={args.policy}",
        flush=True,
    )
    try:
        serve_shadow_runtime(
            runtime,
            listen_socket=args.listen_socket,
            refresh_interval_seconds=args.refresh_interval,
            stop_event=stop,
        )
    except Exception as exc:
        print(f"FAIL: {exc}", flush=True)
        return 2
    print("AlertV2 Stage 4B shadow runtime stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
