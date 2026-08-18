from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
from threading import Event

from .agent import BatchSender, TelemetryAgent
from .core_client import CoreStateClient
from .http_client import AIBridgeTelemetryClient
from .store import TelemetryStore


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_DATABASE = Path("/var/lib/workshop-ventilation/telemetry.sqlite3")
DEFAULT_SOURCE_ID = "workshop-ventilation-cm5-01"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Durable local CM5 telemetry capture with optional synchronization "
            "to the logical AI Bridge / Data Gateway endpoint"
        )
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--ai-bridge-url",
        default=os.getenv("WVC_AI_BRIDGE_URL"),
        help=(
            "Logical telemetry sink base URL, e.g. http://192.168.1.55:8080. "
            "If omitted, local capture remains active and remote sync is disabled. "
            "May use WVC_AI_BRIDGE_URL."
        ),
    )
    parser.add_argument(
        "--source-id",
        default=os.getenv("WVC_TELEMETRY_SOURCE_ID", DEFAULT_SOURCE_ID),
    )
    parser.add_argument("--capture-interval", type=float, default=5.0)
    parser.add_argument("--sync-interval", type=float, default=5.0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--http-timeout", type=float, default=5.0)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        help="Retention for synchronized 5-second RAW samples; pending rows are never removed",
    )
    parser.add_argument(
        "--minute-retention-days",
        type=int,
        default=90,
        help="Retention for local one-minute rollups",
    )
    parser.add_argument(
        "--quarter-retention-days",
        type=int,
        default=730,
        help="Retention for local fifteen-minute rollups",
    )
    parser.add_argument(
        "--maintenance-interval",
        type=float,
        default=60.0,
        help="Seconds between bounded local rollup/retention maintenance passes",
    )
    parser.add_argument(
        "--max-rollup-buckets-per-run",
        type=int,
        default=240,
        help="Maximum catch-up buckets per resolution in one maintenance pass",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Capture one real CoreState snapshot and, if a sink is configured, "
            "synchronize pending data, then exit"
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def build_batch_sender(ai_bridge_url: str | None, http_timeout: float) -> BatchSender | None:
    if not ai_bridge_url:
        return None
    return AIBridgeTelemetryClient(ai_bridge_url, http_timeout)


def main() -> int:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = TelemetryStore(args.database)
    store.initialize()
    sender = build_batch_sender(args.ai_bridge_url, args.http_timeout)
    agent = TelemetryAgent(
        store=store,
        state_reader=CoreStateClient(args.socket),
        batch_sender=sender,
        source_id=args.source_id,
        capture_interval_seconds=args.capture_interval,
        idle_sync_interval_seconds=args.sync_interval,
        batch_size=args.batch_size,
        retention_days=args.retention_days,
        minute_retention_days=args.minute_retention_days,
        quarter_retention_days=args.quarter_retention_days,
        maintenance_interval_seconds=args.maintenance_interval,
        max_rollup_buckets_per_run=args.max_rollup_buckets_per_run,
    )

    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logger = logging.getLogger(__name__)
    if args.once:
        logger.info(
            "Running one-shot real telemetry validation sync_enabled=%s",
            agent.sync_enabled,
        )
        agent.capture_once()
        while agent.sync_once():
            pass
        logger.info("One-shot telemetry validation completed")
        return 0

    logger.info(
        "CM5 telemetry capture started source_id=%s sync_enabled=%s sink=%s "
        "capture_interval=%.3fs raw_retention=%dd minute_retention=%dd "
        "quarter_retention=%dd",
        args.source_id,
        agent.sync_enabled,
        args.ai_bridge_url or "disabled",
        args.capture_interval,
        args.retention_days,
        args.minute_retention_days,
        args.quarter_retention_days,
    )
    agent.run(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
