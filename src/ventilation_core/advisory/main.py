from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
from threading import Event

from .agent import AdvisoryAgent
from .cache import AdvisoryCache
from .client import AIBridgeAdvisoryClient


DEFAULT_CACHE = Path("/var/lib/workshop-ventilation/ai-advisory.json")
DEFAULT_SOURCE_ID = "workshop-ventilation-cm5-01"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only AI advisory delivery from AI Bridge to CM5 local cache"
    )
    parser.add_argument(
        "--ai-bridge-url",
        default=os.getenv("WVC_AI_BRIDGE_URL"),
        help="AI Bridge base URL, e.g. http://192.168.1.55:8080; may use WVC_AI_BRIDGE_URL",
    )
    parser.add_argument(
        "--source-id",
        default=os.getenv("WVC_AI_ADVISORY_SOURCE_ID", DEFAULT_SOURCE_ID),
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("WVC_AI_ADVISORY_POLL_INTERVAL", "60")),
    )
    parser.add_argument("--http-timeout", type=float, default=5.0)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch latest advisory once, update cache if needed, then exit",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.ai_bridge_url:
        raise SystemExit(
            "AI Bridge URL is required: use --ai-bridge-url or WVC_AI_BRIDGE_URL"
        )
    if args.poll_interval <= 0:
        raise SystemExit("AI advisory poll interval must be positive")

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    agent = AdvisoryAgent(
        client=AIBridgeAdvisoryClient(args.ai_bridge_url, args.http_timeout),
        cache=AdvisoryCache(args.cache),
        source_id=args.source_id,
        poll_interval_seconds=args.poll_interval,
    )

    if args.once:
        try:
            changed = agent.fetch_once()
        except Exception as exc:
            logging.getLogger(__name__).error("AI advisory one-shot failed: %s", exc)
            return 1
        logging.getLogger(__name__).info(
            "AI advisory one-shot completed cache_updated=%s", changed
        )
        return 0

    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logging.getLogger(__name__).info(
        "CM5 AI advisory client started source_id=%s ai_bridge=%s poll_interval=%.1fs",
        args.source_id,
        args.ai_bridge_url,
        args.poll_interval,
    )
    agent.run(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
