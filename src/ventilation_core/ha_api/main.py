from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from ventilation_core.web.client import CoreUnixClient

from .app import HaReadOnlyApplication
from .client import CoreReadOnlyGateway
from .server import HaApiHttpServer


DEFAULT_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8082


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WVC read-only API for Home Assistant")
    parser.add_argument("--host", default=os.getenv("WVC_HA_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("WVC_HA_PORT", str(DEFAULT_PORT))))
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path(os.getenv("WVC_CORE_SOCKET", str(DEFAULT_SOCKET))),
    )
    parser.add_argument(
        "--core-timeout",
        type=float,
        default=float(os.getenv("WVC_HA_CORE_TIMEOUT", "5")),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be within 1..65535")
    if args.core_timeout <= 0:
        raise SystemExit("--core-timeout must be positive")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    transport = CoreUnixClient(args.socket, timeout_seconds=args.core_timeout)
    core = CoreReadOnlyGateway(transport)
    app = HaReadOnlyApplication(core)
    server = HaApiHttpServer((args.host, args.port), app)

    logging.getLogger(__name__).info(
        "HA read-only API listening on http://%s:%d using core socket %s; GET-only boundary active",
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
