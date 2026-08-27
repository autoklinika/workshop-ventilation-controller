from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from ventilation_core.alert_policy import DEFAULT_RUNTIME_POLICY_PATH
from ventilation_core.alert_policy_runtime import RuntimeAlertPolicyManager
from ventilation_core.application.alert_registry import AlertRegistry
from ventilation_core.application.alert_v2_policy_service import AlertV2ReadOnlyPolicyService
from ventilation_core.application.service_plane_alert_registry import (
    ServicePlaneCorrelatingAlertRegistry,
)
from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.application.shadow_service import ShadowAlertingVentilationService
from ventilation_core.calendar import (
    CalendarEngine,
    UnavailableCalendarEngine,
    default_calendar_config,
)
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.shadow_policy import ShadowPolicyV1
from ventilation_core.infrastructure.aero_bus_worker import AeroBusConfig, ProcessAeroBus
from ventilation_core.infrastructure.process_actuator import ProcessIsolatedActuator
from ventilation_core.infrastructure.sensor_bus_worker import ProcessSensorBus, SensorBusConfig
from ventilation_core.infrastructure.sqlite_alert_store import SqliteAlertStore
from ventilation_core.infrastructure.sqlite_calendar_store import SqliteCalendarStore
from ventilation_core.infrastructure.system_power_monitor import RaspberryPiSystemPowerMonitor
from ventilation_core.infrastructure.tacho_monitor import TachoMonitor, TachoMonitorConfig
from ventilation_core.infrastructure.zigbee_capability_monitor import CapabilityManagedZigbeeMqttMonitor
from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeDeviceConfig, ZigbeeMqttConfig
from ventilation_core.infrastructure.zigbee_role_store import ZigbeeRoleStore
from ventilation_core.runtime.server import CoreServer
from ventilation_core.service_plane_monitor import (
    DEFAULT_SERVICE_AGENT_SOCKET,
    ServicePlaneMonitor,
)


LOGGER = logging.getLogger(__name__)


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
    parser.add_argument("--socket", type=Path, default=Path("/run/workshop-ventilation/ventilation-core.sock"))
    parser.add_argument("--alerts-db", type=Path, default=Path("/var/lib/workshop-ventilation/alerts.sqlite3"))
    parser.add_argument(
        "--automation-db",
        type=Path,
        default=Path("/var/lib/workshop-ventilation/automation.sqlite3"),
        help="Persistent Calendar Engine and low-churn automation configuration database",
    )
    parser.add_argument(
        "--alert-policy",
        type=Path,
        default=DEFAULT_RUNTIME_POLICY_PATH,
        help="Read-only AlertV2 policy path; invalid/missing policy never changes control behavior",
    )
    parser.add_argument(
        "--service-agent-socket",
        type=Path,
        default=DEFAULT_SERVICE_AGENT_SOCKET,
        help="Read-only local WVC-SERVICE status socket used only for AlertV2 diagnostics",
    )
    parser.add_argument("--service-agent-timeout", type=float, default=0.35)
    parser.add_argument("--service-agent-failure-threshold", type=int, default=3)
    parser.add_argument("--service-node-initial-grace", type=float, default=40.0)
    parser.add_argument("--disable-service-plane-correlation", action="store_true")
    parser.add_argument("--minimum-running-voltage", type=float, default=1.0)
    parser.add_argument("--maximum-voltage", type=float, default=10.0)
    parser.add_argument("--command-timeout", type=float, default=3.0)
    parser.add_argument("--health-interval", type=float, default=1.0)
    parser.add_argument("--hardware-failure-threshold", type=int, default=3)
    parser.add_argument("--system-power-command", default="/usr/bin/vcgencmd")
    parser.add_argument("--system-power-timeout", type=float, default=0.5)
    parser.add_argument("--disable-system-power-monitor", action="store_true")

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

    parser.add_argument("--enable-supply-tacho", action="store_true", help="Enable read-only SUPPLY TACHO feedback on GPIO17 by default")
    parser.add_argument("--enable-extract-tacho", action="store_true", help="Enable read-only EXTRACT TACHO feedback on GPIO27 by default")
    parser.add_argument("--tacho-chip", default="/dev/gpiochip0")
    parser.add_argument("--supply-tacho-line", default="GPIO17")
    parser.add_argument("--extract-tacho-line", default="GPIO27")
    parser.add_argument("--tacho-timeout", type=float, default=0.25)
    parser.add_argument("--tacho-averaging-periods", type=int, default=6)

    parser.add_argument("--zigbee-mqtt-host", default="127.0.0.1")
    parser.add_argument("--zigbee-mqtt-port", type=int, default=1883)
    parser.add_argument("--zigbee-base-topic", default="zigbee2mqtt")
    parser.add_argument("--zigbee-supply-name", default="temp_nawiew")
    parser.add_argument("--zigbee-extract-name", default="temp_wywiew")
    parser.add_argument("--zigbee-supply-ieee", default="")
    parser.add_argument("--zigbee-extract-ieee", default="")
    parser.add_argument(
        "--zigbee-roles-file",
        type=Path,
        default=Path("/var/lib/workshop-ventilation/zigbee-roles.json"),
    )
    parser.add_argument("--disable-zigbee", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


async def run_core(args: argparse.Namespace) -> None:
    alert_registry = None
    service_plane_registry = None
    calendar_engine = None
    actuator = None
    sensor_bus = None
    aero_bus = None
    tacho = None
    zigbee = None
    system_power_monitor = None
    service = None
    try:
        alert_registry = AlertRegistry(SqliteAlertStore(args.alerts_db))
        if not args.disable_service_plane_correlation:
            service_plane_monitor = ServicePlaneMonitor(
                args.service_agent_socket,
                timeout_seconds=args.service_agent_timeout,
            )
            service_plane_registry = ServicePlaneCorrelatingAlertRegistry(
                alert_registry,
                service_plane_monitor,
                agent_failure_threshold=args.service_agent_failure_threshold,
                node_initial_grace_seconds=args.service_node_initial_grace,
            )
            alert_registry = service_plane_registry

        try:
            calendar_engine = CalendarEngine(
                SqliteCalendarStore(
                    args.automation_db,
                    initial_config=default_calendar_config(),
                )
            )
        except Exception as exc:
            LOGGER.exception(
                "Persistent Calendar Engine store unavailable; continuing with explicit unavailable calendar state"
            )
            calendar_engine = UnavailableCalendarEngine(str(exc))

        actuator = ProcessIsolatedActuator(
            bus=args.bus,
            address=args.address,
            timeout_seconds=args.command_timeout,
        )

        if not args.disable_system_power_monitor:
            system_power_monitor = RaspberryPiSystemPowerMonitor(
                command=(args.system_power_command, "get_throttled"),
                timeout_seconds=args.system_power_timeout,
            )

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
        if args.enable_supply_tacho or args.enable_extract_tacho:
            tacho = TachoMonitor(
                TachoMonitorConfig(
                    chip_path=args.tacho_chip,
                    supply_line_name=args.supply_tacho_line if args.enable_supply_tacho else None,
                    extract_line_name=args.extract_tacho_line if args.enable_extract_tacho else None,
                    timeout_seconds=args.tacho_timeout,
                    averaging_periods=args.tacho_averaging_periods,
                )
            )

        if not args.disable_zigbee:
            try:
                seed_devices = (
                    ZigbeeDeviceConfig(
                        role="supply",
                        friendly_name=args.zigbee_supply_name,
                        ieee_address=args.zigbee_supply_ieee or None,
                    ),
                    ZigbeeDeviceConfig(
                        role="extract",
                        friendly_name=args.zigbee_extract_name,
                        ieee_address=args.zigbee_extract_ieee or None,
                    ),
                )
                role_store = ZigbeeRoleStore(args.zigbee_roles_file)
                runtime_devices = role_store.load_or_seed(seed_devices)
                zigbee = CapabilityManagedZigbeeMqttMonitor(
                    ZigbeeMqttConfig(
                        broker_host=args.zigbee_mqtt_host,
                        broker_port=args.zigbee_mqtt_port,
                        base_topic=args.zigbee_base_topic,
                        devices=runtime_devices,
                    ),
                    role_store=role_store,
                )
            except Exception:
                LOGGER.exception("Unable to initialize Zigbee MQTT monitor; continuing without Zigbee")
                zigbee = None

        required_tacho_channels = tuple(
            channel
            for channel, enabled in (
                ("supply", args.enable_supply_tacho),
                ("extract", args.enable_extract_tacho),
            )
            if enabled
        )
        legacy_service = ShadowAlertingVentilationService(
            actuator=actuator,
            policy=FanSetpointPolicy(
                minimum_running_voltage=args.minimum_running_voltage,
                maximum_voltage=args.maximum_voltage,
            ),
            hardware_failure_threshold=args.hardware_failure_threshold,
            sensor_bus=sensor_bus,
            aero_bus=aero_bus,
            tacho=tacho,
            zigbee=zigbee,
            calendar_engine=calendar_engine,
            alert_registry=alert_registry,
            required_tacho_channels=required_tacho_channels,
            system_power_monitor=system_power_monitor,
            shadow_evaluator=PolicyShadowAutomationEvaluator(ShadowPolicyV1()),
        )
        alert_policy_manager = RuntimeAlertPolicyManager(args.alert_policy)
        service = AlertV2ReadOnlyPolicyService(
            legacy_service,
            alert_policy_manager,
            service_plane_diagnostics=(
                None if service_plane_registry is None else service_plane_registry.diagnostics
            ),
        )
        if alert_policy_manager.loaded:
            metadata = alert_policy_manager.metadata()
            LOGGER.info(
                "AlertV2 runtime mapping active version=%s sha256=%s; control policy remains disabled",
                metadata["policy_version"],
                metadata["sha256"],
            )
        else:
            LOGGER.warning(
                "AlertV2 runtime policy unavailable; legacy alert behavior continues unchanged: %s",
                alert_policy_manager.metadata()["last_error"],
            )
        if service_plane_registry is not None:
            LOGGER.info(
                "AlertV2 Service Plane correlation enabled read-only socket=%s; control policy remains disabled",
                args.service_agent_socket,
            )
        if system_power_monitor is not None:
            LOGGER.info(
                "Raspberry Pi system power monitor enabled read-only command=%s get_throttled",
                args.system_power_command,
            )
        server = CoreServer(
            service=service,
            socket_path=args.socket,
            health_interval_seconds=args.health_interval,
        )
    except BaseException:
        if service is not None:
            service.close()
        else:
            try:
                if zigbee is not None:
                    zigbee.close()
            finally:
                try:
                    if tacho is not None:
                        tacho.close()
                finally:
                    try:
                        if aero_bus is not None:
                            aero_bus.close()
                    finally:
                        try:
                            if sensor_bus is not None:
                                sensor_bus.close()
                        finally:
                            try:
                                if system_power_monitor is not None:
                                    system_power_monitor.close()
                            finally:
                                try:
                                    if actuator is not None:
                                        actuator.close()
                                finally:
                                    try:
                                        if calendar_engine is not None:
                                            calendar_engine.close()
                                    finally:
                                        if alert_registry is not None:
                                            alert_registry.close()
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
