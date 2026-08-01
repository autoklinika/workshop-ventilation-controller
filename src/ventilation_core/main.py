from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from ventilation_core.application.service import VentilationService
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.infrastructure.process_actuator import ProcessIsolatedActuator
from ventilation_core.runtime.server import CoreServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop ventilation control core")
    parser.add_argument("--bus", type=int, default=1)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x58)
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path("/run/workshop-ventilation/ventilation-core.sock"),
    )
    parser.add_argument("--minimum-running-voltage", type=float, default=1.0)
    parser.add_argument("--maximum-voltage", type=float, default=10.0)
    parser.add_argument("--command-timeout", type=float, default=3.0)
    parser.add_argument("--health-interval", type=float, default=1.0)
    parser.add_argument("--log-level", default="INFO")
    return parser


async def run_core(args: argparse.Namespace) -> None:
    actuator = ProcessIsolatedActuator(
        bus=args.bus,
        address=args.address,
        timeout_seconds=args.command_timeout,
    )
    service = VentilationService(
        actuator=actuator,
        policy=FanSetpointPolicy(
            minimum_running_voltage=args.minimum_running_voltage,
            maximum_voltage=args.maximum_voltage,
        ),
    )
    server = CoreServer(
        service=service,
        socket_path=args.socket,
        health_interval_seconds=args.health_interval,
    )
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, server.request_shutdown)
    await server.run()


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_core(args))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
