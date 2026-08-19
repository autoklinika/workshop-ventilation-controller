from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from ventilation_core.telemetry.long_range_history import LongRangeTelemetryHistoryReader

from .advisory import FileAdvisoryProvider
from .app import WebApplication
from .client import CoreUnixClient
from .config import WebUiConfig
from .server import WebUiHttpServer
from .weather import FileWeatherProvider


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_TELEMETRY_DATABASE = Path("/var/lib/workshop-ventilation/telemetry.sqlite3")
DEFAULT_WEATHER_SNAPSHOT = Path("/var/lib/workshop-ventilation/weather.json")
DEFAULT_AI_ADVISORY_CACHE = Path("/var/lib/workshop-ventilation/ai-advisory.json")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8088


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop Ventilation web UI")
    parser.add_argument("--host", default=os.getenv("WVC_WEB_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("WVC_WEB_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--socket", type=Path, default=Path(os.getenv("WVC_CORE_SOCKET", str(DEFAULT_SOCKET))))
    parser.add_argument("--core-timeout", type=float, default=float(os.getenv("WVC_WEB_CORE_TIMEOUT", "70")))
    parser.add_argument(
        "--telemetry-database",
        type=Path,
        default=Path(os.getenv("WVC_WEB_TELEMETRY_DATABASE", str(DEFAULT_TELEMETRY_DATABASE))),
        help="Read-only local telemetry history database",
    )
    parser.add_argument(
        "--weather-snapshot",
        type=Path,
        default=Path(os.getenv("WVC_WEB_WEATHER_SNAPSHOT", str(DEFAULT_WEATHER_SNAPSHOT))),
        help="Read-only local snapshot written by wvc-weather.service",
    )
    parser.add_argument(
        "--ai-advisory-cache",
        type=Path,
        default=Path(os.getenv("WVC_WEB_AI_ADVISORY_CACHE", str(DEFAULT_AI_ADVISORY_CACHE))),
        help="Read-only local AI advisory cache written by wvc-ai-advisory.service",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be within 1..65535")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    static_root = Path(__file__).with_name("static")
    core = CoreUnixClient(args.socket, timeout_seconds=args.core_timeout)
    history = LongRangeTelemetryHistoryReader(args.telemetry_database)
    weather = FileWeatherProvider(args.weather_snapshot)
    advisory = FileAdvisoryProvider(
        args.ai_advisory_cache,
        expected_source_id=os.getenv(
            "WVC_AI_ADVISORY_SOURCE_ID",
            "workshop-ventilation-cm5-01",
        ),
    )
    app = WebApplication(
        core,
        WebUiConfig.from_environment(),
        weather,
        history,
        advisory,
    )
    server = WebUiHttpServer((args.host, args.port), app, static_root)

    logging.getLogger(__name__).info(
        "web UI listening on http://%s:%d using core socket %s; history=%s; weather_snapshot=%s; ai_advisory_cache=%s",
        args.host,
        args.port,
        args.socket,
        args.telemetry_database,
        args.weather_snapshot,
        args.ai_advisory_cache,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
