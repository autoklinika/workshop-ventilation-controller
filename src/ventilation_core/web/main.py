from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from ventilation_core.telemetry.long_range_history import LongRangeTelemetryHistoryReader

from .advisory import FileAdvisoryProvider
from .alert_history import SqliteAlertHistoryReader
from .alert_history_app import AlertHistoryWebApplication
from .client import CoreUnixClient
from .config import WebUiConfig
from .control_engine_app import ControlEngineWebApplication
from .host_power import DEFAULT_HOST_POWER_SOCKET, HostPowerClient
from .server import WebUiHttpServer
from .service_status import ServiceStatusProvider
from .weather import FileWeatherProvider


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_TELEMETRY_DATABASE = Path("/var/lib/workshop-ventilation/telemetry.sqlite3")
DEFAULT_ALERT_DATABASE = Path("/var/lib/workshop-ventilation/alerts.sqlite3")
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
        "--alert-database",
        type=Path,
        default=Path(os.getenv("WVC_WEB_ALERT_DATABASE", str(DEFAULT_ALERT_DATABASE))),
        help="Read-only local alert journal database",
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
    alert_history = SqliteAlertHistoryReader(args.alert_database)
    weather = FileWeatherProvider(args.weather_snapshot)
    advisory = FileAdvisoryProvider(
        args.ai_advisory_cache,
        expected_source_id=os.getenv(
            "WVC_AI_ADVISORY_SOURCE_ID",
            "workshop-ventilation-cm5-01",
        ),
    )
    service_status = ServiceStatusProvider(
        core,
        telemetry_database=args.telemetry_database,
        alert_database=args.alert_database,
        advisory=advisory,
        ai_server_host=os.getenv("WVC_AI_SERVER_HOST", "192.168.1.55"),
        ai_server_port=int(os.getenv("WVC_AI_SERVER_PORT", "8080")),
    )
    host_power = HostPowerClient(
        Path(os.getenv("WVC_HOST_POWER_SOCKET", str(DEFAULT_HOST_POWER_SOCKET)))
    )
    # ControlEngineWebApplication deliberately extends the existing
    # AlertHistoryWebApplication contract instead of replacing that functionality.
    app: AlertHistoryWebApplication = ControlEngineWebApplication(
        core,
        WebUiConfig.from_environment(),
        weather,
        history,
        advisory,
        alert_history=alert_history,
        service_status=service_status,
        host_power=host_power,
    )
    server = WebUiHttpServer((args.host, args.port), app, static_root)

    logging.getLogger(__name__).info(
        "web UI listening on http://%s:%d using core socket %s; history=%s; alert_history=%s; weather_snapshot=%s; ai_advisory_cache=%s; service_dashboard=read-only; host_power_socket=%s; control_engine=shadow-config-only",
        args.host,
        args.port,
        args.socket,
        args.telemetry_database,
        args.alert_database,
        args.weather_snapshot,
        args.ai_advisory_cache,
        host_power.socket_path,
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
