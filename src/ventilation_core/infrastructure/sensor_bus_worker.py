from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from multiprocessing.queues import Queue
from threading import RLock
from typing import Any

from ventilation_core.domain.sensors import (
    AirQualityReading,
    SensorBusState,
    SensorNodeState,
)
from ventilation_core.infrastructure.modbus_rtu import ModbusError, read_input_registers
from ventilation_core.infrastructure.sen55_modbus import (
    EXPECTED_MAP_VERSION,
    REGISTER_COUNT,
    UnsupportedMapVersion,
    decode_sensor_registers,
)


LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SensorBusConfig:
    port: str = "/dev/ttyAMA0"
    addresses: tuple[int, ...] = (1, 2)
    baudrate: int = 19200
    timeout_seconds: float = 0.5
    poll_interval_seconds: float = 1.0
    inter_node_delay_seconds: float = 0.010
    reconnect_delay_seconds: float = 1.0
    expected_map_version: int = EXPECTED_MAP_VERSION

    def __post_init__(self) -> None:
        if not self.port:
            raise ValueError("Sensor bus port cannot be empty")
        if not self.addresses or len(set(self.addresses)) != len(self.addresses):
            raise ValueError("Sensor bus addresses must be non-empty and unique")
        if any(not 1 <= address <= 247 for address in self.addresses):
            raise ValueError("Sensor bus addresses must be in range 1..247")
        if self.baudrate <= 0:
            raise ValueError("Sensor bus baudrate must be positive")
        if self.timeout_seconds <= 0 or self.poll_interval_seconds <= 0:
            raise ValueError("Sensor bus timeout and poll interval must be positive")
        if self.inter_node_delay_seconds < 0 or self.reconnect_delay_seconds <= 0:
            raise ValueError("Invalid sensor bus delay configuration")


def _initial_state(config: SensorBusConfig) -> SensorBusState:
    return SensorBusState(
        port=config.port,
        baudrate=config.baudrate,
        addresses=config.addresses,
        expected_map_version=config.expected_map_version,
        inter_node_delay_seconds=config.inter_node_delay_seconds,
        poll_interval_seconds=config.poll_interval_seconds,
        nodes=tuple(SensorNodeState(slave_address=address) for address in config.addresses),
    )


def _publish_latest(state_queue: Queue, state: SensorBusState) -> None:
    while True:
        try:
            state_queue.put_nowait(state)
            return
        except queue.Full:
            try:
                state_queue.get_nowait()
            except queue.Empty:
                return


def _unsupported_map_state(
    previous: SensorNodeState,
    polls: int,
    error: UnsupportedMapVersion,
) -> SensorNodeState:
    return SensorNodeState(
        slave_address=previous.slave_address,
        online=True,
        usable=False,
        measurement_valid=False,
        measurement_stale=True,
        sensor_present=False,
        reading=AirQualityReading(),
        map_version=error.received,
        last_success_at=_now_iso(),
        last_error=str(error),
        polls=polls,
        successful_polls=previous.successful_polls + 1,
        communication_errors=previous.communication_errors,
        consecutive_failures=0,
        invalid_measurements=previous.invalid_measurements,
        stale_measurements=previous.stale_measurements,
        map_version_errors=previous.map_version_errors + 1,
    )


def _poll_node(port: Any, config: SensorBusConfig, previous: SensorNodeState) -> SensorNodeState:
    polls = previous.polls + 1
    try:
        registers = read_input_registers(
            port,
            slave_address=previous.slave_address,
            start_address=0,
            quantity=REGISTER_COUNT,
            timeout_seconds=config.timeout_seconds,
        )
        sample = decode_sensor_registers(
            registers,
            expected_map_version=config.expected_map_version,
        )
        diagnostics_failures = (
            0
            if not sample.sen55_device_status_supported
            or sample.sen55_device_status_valid
            else previous.sen55_diagnostics_failures + 1
        )
        return SensorNodeState(
            slave_address=previous.slave_address,
            online=True,
            usable=sample.measurement_valid,
            measurement_valid=sample.measurement_valid,
            measurement_stale=sample.measurement_stale,
            sensor_present=sample.sensor_present,
            availability_mask=sample.availability_mask,
            status_mask=sample.status_mask,
            reading=sample.reading,
            age_seconds=sample.age_seconds,
            sensor_errors=sample.sensor_errors,
            modbus_service_errors=sample.modbus_service_errors,
            uptime_seconds=sample.uptime_seconds,
            firmware_version=sample.firmware_version,
            map_version=sample.map_version,
            sequence=sample.sequence,
            last_success_at=_now_iso(),
            last_error=None,
            polls=polls,
            successful_polls=previous.successful_polls + 1,
            communication_errors=previous.communication_errors,
            consecutive_failures=0,
            invalid_measurements=(
                previous.invalid_measurements + (0 if sample.measurement_valid else 1)
            ),
            stale_measurements=(
                previous.stale_measurements + (1 if sample.measurement_stale else 0)
            ),
            map_version_errors=previous.map_version_errors,
            sen55_device_status_supported=sample.sen55_device_status_supported,
            sen55_device_status_valid=sample.sen55_device_status_valid,
            sen55_fan_speed_warning=sample.sen55_fan_speed_warning,
            sen55_fan_cleaning=sample.sen55_fan_cleaning,
            sen55_gas_sensor_error=sample.sen55_gas_sensor_error,
            sen55_rht_error=sample.sen55_rht_error,
            sen55_laser_error=sample.sen55_laser_error,
            sen55_fan_error=sample.sen55_fan_error,
            sen55_diagnostics_failures=diagnostics_failures,
        )
    except UnsupportedMapVersion as exc:
        return _unsupported_map_state(previous, polls, exc)
    except (ModbusError, ValueError) as exc:
        return replace(
            previous,
            online=False,
            usable=False,
            last_error=str(exc),
            polls=polls,
            communication_errors=previous.communication_errors + 1,
            consecutive_failures=previous.consecutive_failures + 1,
        )


def run_sensor_bus_worker(config: SensorBusConfig, state_queue: Queue, stop_event: Any) -> None:
    state = _initial_state(config)
    nodes = {node.slave_address: node for node in state.nodes}

    while not stop_event.is_set():
        try:
            import serial

            with serial.Serial(
                port=config.port,
                baudrate=config.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=config.timeout_seconds,
                write_timeout=config.timeout_seconds,
                exclusive=True,
            ) as port:
                state = replace(
                    state,
                    ready=True,
                    worker_alive=True,
                    last_error=None,
                    nodes=tuple(nodes[address] for address in config.addresses),
                )
                _publish_latest(state_queue, state)

                while not stop_event.is_set():
                    for index, address in enumerate(config.addresses):
                        try:
                            nodes[address] = _poll_node(port, config, nodes[address])
                        except serial.SerialException:
                            raise
                        if (
                            index + 1 < len(config.addresses)
                            and config.inter_node_delay_seconds > 0
                            and stop_event.wait(config.inter_node_delay_seconds)
                        ):
                            break

                    state = replace(
                        state,
                        ready=True,
                        worker_alive=True,
                        last_cycle_at=_now_iso(),
                        last_error=None,
                        nodes=tuple(nodes[address] for address in config.addresses),
                    )
                    _publish_latest(state_queue, state)
                    if stop_event.wait(config.poll_interval_seconds):
                        break
        except Exception as exc:
            state = replace(
                state,
                ready=False,
                worker_alive=True,
                last_error=f"{type(exc).__name__}: {exc}",
                nodes=tuple(nodes[address] for address in config.addresses),
            )
            _publish_latest(state_queue, state)
            if stop_event.wait(config.reconnect_delay_seconds):
                break


class ProcessSensorBus:
    """Supervised sensor polling process and sole owner of the SENSOR BUS UART."""

    def __init__(self, config: SensorBusConfig) -> None:
        self._config = config
        self._context = mp.get_context("spawn")
        self._state_queue = self._context.Queue(maxsize=4)
        self._stop_event = self._context.Event()
        self._process: mp.Process | None = None
        self._state = _initial_state(config)
        self._worker_restarts = 0
        self._lock = RLock()
        self._start_worker()

    def state(self) -> SensorBusState:
        with self._lock:
            self._drain_updates()
            alive = self._process is not None and self._process.is_alive()
            return replace(
                self._state,
                worker_alive=alive,
                worker_restarts=self._worker_restarts,
            )

    def health_check(self) -> None:
        with self._lock:
            self._drain_updates()
            if self._process is not None and self._process.is_alive():
                return
            exit_code = None if self._process is None else self._process.exitcode
            self._state = replace(
                self._state,
                ready=False,
                worker_alive=False,
                last_error=f"Sensor bus worker exited with code {exit_code}",
            )
            self._dispose_process()
            self._discard_queued_states()
            self._worker_restarts += 1
            self._start_worker()

    def close(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._process is not None:
                self._process.join(timeout=3.0)
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=1.0)
            self._dispose_process()
            self._discard_queued_states()
            self._state_queue.close()
            self._state_queue.join_thread()
            self._state = replace(self._state, ready=False, worker_alive=False)

    def _start_worker(self) -> None:
        self._stop_event.clear()
        self._process = self._context.Process(
            target=run_sensor_bus_worker,
            args=(self._config, self._state_queue, self._stop_event),
            name="sensor-bus-worker",
            daemon=True,
        )
        self._process.start()
        LOGGER.info(
            "Started SENSOR BUS worker pid=%s port=%s addresses=%s",
            self._process.pid,
            self._config.port,
            self._config.addresses,
        )

    def _dispose_process(self) -> None:
        if self._process is None:
            return
        try:
            self._process.join(timeout=0)
            self._process.close()
        finally:
            self._process = None

    def _discard_queued_states(self) -> None:
        while True:
            try:
                self._state_queue.get_nowait()
            except queue.Empty:
                return

    def _drain_updates(self) -> None:
        while True:
            try:
                self._state = self._state_queue.get_nowait()
            except queue.Empty:
                return
