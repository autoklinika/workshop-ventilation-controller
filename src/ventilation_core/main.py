from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from ventilation_core.application.service import VentilationService
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.infrastructure.aero_bus_worker import (
    AeroBusConfig,
    ProcessAeroBus,
)
from ventilation_core.infrastructure.process_actuator import ProcessIsolatedActuator
from ventilation_core.infrastructure.sensor_bus_worker import (
    ProcessSensorBus,
    SensorBusConfig,
)
from ventilation_core.runtime.server import CoreServer


def parse_sensor_addresses(value: str) -> tuple[int, ...]:
    addresses: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        address = int(item, 10)
        if not 1 <= address <= 247:
            raise argparse.ArgumentTypeError("Sensor address must be in range 1..247")
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise argparse.ArgumentTypeError("At least one sensor address is required")
    return tuple(addresses)


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
    parser.add_argument("--hardware-failure-threshold", type=int, default=3)

    parser.add_argument("--sensor-port", default="/dev/ttyAMA0")
    parser.add_argument("--sensor-addresses", type=parse_sensor_addresses, default=(1, 2))
    parser.add_argument("--sensor-baud", type=int, default=19200)
    parser.add_argument("--sensor-timeout", type=float, default=0.5)
    parser.add_argument("--sensor-poll-interval", type=float, default=1.0)
    parser.add_argument("--sensor-inter-node-delay", type=float, default=0.010)
    parser.add_argument("--sensor-reconnect-delay", type=float, default=1.0)
    parser.add_argument("--disable-sensor-bus", action="store_true")

    parser.add_argument("--aero-port", default="/dev/ttyAMA4")
    parser.add_argument("--aero-address", type=int, default=44)
    parser.add_argument("--aero-baud", type=int, default=9600)
    parser.add_argument("--aero-timeout", type=float, default=0.5)
    parser.add_argument("--aero-poll-interval", type=float, default=2.0)
    parser.add_argument("--aero-inter-register-delay", type=float, default=0.050)
    parser.add_argument("--aero-reconnect-delay", type=float, default=1.0)
    parser.add_argument("--disable-aero-bus", action="store_true")

    parser.add_argument("--log-level", default="INFO")
    return parser


async def run_core(args: argparse.Namespace) -> None:
    actuator = ProcessIsolatedActuator(
        bus=args.bus,
        address=args.address,
        timeout_seconds=args.command_timeout,
    )
    sensor_bus = None
    aero_bus = None
    try:
        if not args.disable_sensor_bus:
            sensor_bus = ProcessSensorBus(
                SensorBusConfig(
                    port=args.sensor_port,
                    addresses=args.sensor_addresses,
                    baudrate=args.sensor_baud,
                    timeout_seconds=args.sensor_timeout,
                    poll_interval_seconds=args.sensor_poll_interval,
                    inter_node_delay_seconds=args.sensor_inter_node_delay,
                    reconnect_delay_seconds=args.sensor_reconnect_delay,
                )
            )
        if not args.disable_aero_bus:
            aero_bus = ProcessAeroBus(
                AeroBusConfig(
                    port=args.aero_port,
                    slave_address=args.aero_address,
                    baudrate=args.aero_baud,
                    timeout_seconds=args.aero_timeout,
                    poll_interval_seconds=args.aero_poll_interval,
                    inter_register_delay_seconds=args.aero_inter_register_delay,
                    reconnect_delay_seconds=args.aero_reconnect_delay,
                )
            )
        service = VentilationService(
            actuator=actuator,
            policy=FanSetpointPolicy(
                minimum_running_voltage=args.minimum_running_voltage,
                maximum_voltage=args.maximum_voltage,
            ),
            hardware_failure_threshold=args.hardware_failure_threshold,
            sensor_bus=sensor_bus,
            aero_bus=aero_bus,
        )
        server = CoreServer(
            service=service,
            socket_path=args.socket,
            health_interval_seconds=args.health_interval,
        )
    except BaseException:
        try:
            if aero_bus is not None:
                aero_bus.close()
        finally:
            try:
                if sensor_bus is not None:
                    sensor_bus.close()
            finally:
                actuator.close()
        raise

    loop = asyncio.get_running_loop()
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, server.request_shutdown)
    except BaseException:
        await asyncio.to_thread(service.close)
        raise
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
