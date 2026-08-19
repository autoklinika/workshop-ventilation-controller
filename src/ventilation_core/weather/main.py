from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
from threading import Event

from .agent import WeatherAgent
from .cache import WeatherCache
from .provider import MetNoWeatherClient, WeatherConfig


DEFAULT_CACHE = Path("/var/lib/workshop-ventilation/weather.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independent CM5 weather acquisition service"
    )
    parser.add_argument(
        "--latitude",
        type=float,
        default=os.getenv("WVC_WEATHER_LATITUDE") or None,
    )
    parser.add_argument(
        "--longitude",
        type=float,
        default=os.getenv("WVC_WEATHER_LONGITUDE") or None,
    )
    parser.add_argument(
        "--label",
        default=os.getenv("WVC_WEATHER_LABEL", "Warsztat"),
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("WVC_WEATHER_USER_AGENT", ""),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(os.getenv("WVC_WEATHER_CACHE", str(DEFAULT_CACHE))),
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("WVC_WEATHER_POLL_INTERVAL", "3600")),
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=float(os.getenv("WVC_WEATHER_HTTP_TIMEOUT", "5")),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.latitude is None or args.longitude is None:
        raise SystemExit(
            "weather coordinates are required: set WVC_WEATHER_LATITUDE and WVC_WEATHER_LONGITUDE"
        )
    if not args.user_agent.strip():
        raise SystemExit("WVC_WEATHER_USER_AGENT is required")
    if args.poll_interval <= 0:
        raise SystemExit("weather poll interval must be positive")

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = WeatherConfig(
        latitude=args.latitude,
        longitude=args.longitude,
        label=args.label,
        user_agent=args.user_agent,
        timeout_seconds=args.http_timeout,
    )
    agent = WeatherAgent(
        client=MetNoWeatherClient(config),
        cache=WeatherCache(args.cache),
        poll_interval_seconds=args.poll_interval,
    )

    if args.once:
        try:
            snapshot = agent.fetch_once()
        except Exception as exc:
            logging.getLogger(__name__).error("weather one-shot failed: %s", exc)
            return 1
        logging.getLogger(__name__).info(
            "weather one-shot completed location=%s observed_at=%s",
            snapshot.get("location"),
            snapshot.get("observed_at"),
        )
        return 0

    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logging.getLogger(__name__).info(
        "CM5 weather service started location=%s poll_interval=%.1fs cache=%s",
        args.label,
        args.poll_interval,
        args.cache,
    )
    agent.run(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
