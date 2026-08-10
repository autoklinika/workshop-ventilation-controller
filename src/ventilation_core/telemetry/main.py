from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
from threading import Event

from .agent import TelemetryAgent
from .core_client import CoreStateClient
from .http_client import AIBridgeTelemetryClient
from .store import TelemetryStore


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_DATABASE = Path("/var/lib/workshop-ventilation/telemetry.sqlite3")
DEFAULT_SOURCE_ID = "workshop-ventilation-cm5-01"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Durable read-only telemetry synchronization from CM5 to AI Bridge"
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--ai-bridge-url",
        default=os.getenv("WVC_AI_BRIDGE_URL"),
        help="AI Bridge base URL, e.g. http://192.168.1.55:8080; may use WVC_AI_BRIDGE_URL",
    )
    parser.add_argument(
        "--source-id",
        default=os.getenv("WVC_TELEMETRY_SOURCE_ID", DEFAULT_SOURCE_ID),
    )
    parser.add_argument("--capture-interval", type=float, default=5.0)
    parser.add_argument("--sync-interval", type=float, default=5.0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--http-timeout", type=float, default=5.0)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Capture one real CoreState snapshot, synchronize pending data, then exit",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.ai_bridge_url:
        raise SystemExit(
            "AI Bridge URL is required: use --ai-bridge-url or WVC_AI_BRIDGE_URL"
        )

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = TelemetryStore(args.database)
    store.initialize()
    agent = TelemetryAgent(
        store=store,
        state_reader=CoreStateClient(args.socket),
        batch_sender=AIBridgeTelemetryClient(args.ai_bridge_url, args.http_timeout),
        source_id=args.source_id,
        capture_interval_seconds=args.capture_interval,
        idle_sync_interval_seconds=args.sync_interval,
        batch_size=args.batch_size,
        retention_days=args.retention_days,
    )

    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logger = logging.getLogger(__name__)
    if args.once:
        logger.info("Running one-shot real telemetry validation")
        agent.capture_once()
        while agent.sync_once():
            pass
        logger.info("One-shot telemetry validation completed")
        return 0

    logger.info(
        "CM5 telemetry sync started source_id=%s ai_bridge=%s capture_interval=%.3fs",
        args.source_id,
        args.ai_bridge_url,
        args.capture_interval,
    )
    agent.run(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
