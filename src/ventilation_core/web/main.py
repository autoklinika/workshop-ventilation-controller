from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .app import WebApplication
from .client import CoreUnixClient
from .config import WebUiConfig
from .server import WebUiHttpServer


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8088


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop Ventilation web UI")
    parser.add_argument("--host", default=os.getenv("WVC_WEB_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("WVC_WEB_PORT", str(DEFAULT_PORT))),
    )
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path(os.getenv("WVC_CORE_SOCKET", str(DEFAULT_SOCKET))),
    )
    parser.add_argument(
        "--core-timeout",
        type=float,
        default=float(os.getenv("WVC_WEB_CORE_TIMEOUT", "70")),
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
    app = WebApplication(core, WebUiConfig.from_environment())
    server = WebUiHttpServer((args.host, args.port), app, static_root)

    logging.getLogger(__name__).info(
        "web UI listening on http://%s:%d using core socket %s",
        args.host,
        args.port,
        args.socket,
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
