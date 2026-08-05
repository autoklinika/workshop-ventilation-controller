from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from multiprocessing.queues import Queue
from threading import RLock
from typing import Any

from ventilation_core.domain.aero import AeroBusState, AeroTelemetry
from ventilation_core.infrastructure.aero4a2 import (
    CONFIRMED_TELEMETRY_REGISTERS,
    AeroTelemetryError,
    decode_aero_telemetry,
)
from ventilation_core.infrastructure.modbus_rtu import (
    ModbusError,
    read_holding_registers,
)


LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AeroBusConfig:
    port: str = "/dev/ttyAMA4"
    slave_address: int = 44
    baudrate: int = 9600
    timeout_seconds: float = 0.5
    poll_interval_seconds: float = 2.0
    inter_register_delay_seconds: float = 0.050
    reconnect_delay_seconds: float = 1.0
    register_addresses: tuple[int, ...] = CONFIRMED_TELEMETRY_REGISTERS

    def __post_init__(self) -> None:
        if not self.port:
            raise ValueError("AERO BUS port cannot be empty")
        if not 1 <= self.slave_address <= 247:
            raise ValueError("AERO BUS slave address must be in range 1..247")
        if self.baudrate <= 0:
            raise ValueError("AERO BUS baudrate must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("AERO BUS timeout must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("AERO BUS poll interval must be positive")
        if self.inter_register_delay_seconds < 0:
            raise ValueError("AERO BUS inter-register delay cannot be negative")
        if self.reconnect_delay_seconds <= 0:
            raise ValueError("AERO BUS reconnect delay must be positive")
        if (
            not self.register_addresses
            or len(set(self.register_addresses)) != len(self.register_addresses)
        ):
            raise ValueError("AERO BUS register addresses must be non-empty and unique")
        if any(not 0 <= address <= 0xFFFF for address in self.register_addresses):
            raise ValueError("AERO BUS register address outside Modbus range")


def _initial_state(config: AeroBusConfig) -> AeroBusState:
    return AeroBusState(
        port=config.port,
        baudrate=config.baudrate,
        slave_address=config.slave_address,
        register_addresses=config.register_addresses,
        inter_register_delay_seconds=config.inter_register_delay_seconds,
        poll_interval_seconds=config.poll_interval_seconds,
    )


def _publish_latest(state_queue: Queue, state: AeroBusState) -> None:
    while True:
        try:
            state_queue.put_nowait(state)
            return
        except queue.Full:
            try:
                state_queue.get_nowait()
            except queue.Empty:
                return


def _read_confirmed_snapshot(port: Any, config: AeroBusConfig) -> dict[int, int]:
    snapshot: dict[int, int] = {}
    for index, address in enumerate(config.register_addresses):
        values = read_holding_registers(
            port,
            slave_address=config.slave_address,
            start_address=address,
            quantity=1,
            timeout_seconds=config.timeout_seconds,
        )
        snapshot[address] = values[0]
        if (
            index + 1 < len(config.register_addresses)
            and config.inter_register_delay_seconds > 0
        ):
            time.sleep(config.inter_register_delay_seconds)
    return snapshot


def _poll_aero(
    port: Any,
    config: AeroBusConfig,
    previous: AeroBusState,
) -> AeroBusState:
    polls = previous.polls + 1
    try:
        registers = _read_confirmed_snapshot(port, config)
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

    timestamp = _now_iso()
    try:
        telemetry = decode_aero_telemetry(registers)
    except AeroTelemetryError as exc:
        return replace(
            previous,
            online=True,
            usable=False,
            telemetry=AeroTelemetry(),
            last_success_at=timestamp,
            last_error=str(exc),
            polls=polls,
            successful_polls=previous.successful_polls + 1,
            consecutive_failures=0,
            invalid_samples=previous.invalid_samples + 1,
        )

    return replace(
        previous,
        online=True,
        usable=True,
        telemetry=telemetry,
        last_success_at=timestamp,
        last_error=None,
        polls=polls,
        successful_polls=previous.successful_polls + 1,
        consecutive_failures=0,
    )


def run_aero_bus_worker(
    config: AeroBusConfig,
    state_queue: Queue,
    stop_event: Any,
) -> None:
    state = _initial_state(config)

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
                )
                _publish_latest(state_queue, state)

                while not stop_event.is_set():
                    state = _poll_aero(port, config, state)
                    state = replace(
                        state,
                        ready=True,
                        worker_alive=True,
                        last_cycle_at=_now_iso(),
                    )
                    _publish_latest(state_queue, state)
                    if stop_event.wait(config.poll_interval_seconds):
                        break
        except Exception as exc:
            state = replace(
                state,
                ready=False,
                worker_alive=True,
                online=False,
                usable=False,
                last_error=f"{type(exc).__name__}: {exc}",
            )
            _publish_latest(state_queue, state)
            if stop_event.wait(config.reconnect_delay_seconds):
                break


class ProcessAeroBus:
    """Supervised read-only AERO BUS process and sole owner of its UART."""

    def __init__(self, config: AeroBusConfig) -> None:
        self._config = config
        self._context = mp.get_context("spawn")
        self._state_queue = self._context.Queue(maxsize=4)
        self._stop_event = self._context.Event()
        self._process: mp.Process | None = None
        self._state = _initial_state(config)
        self._worker_restarts = 0
        self._lock = RLock()
        self._start_worker()

    def state(self) -> AeroBusState:
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
                online=False,
                usable=False,
                last_error=f"AERO BUS worker exited with code {exit_code}",
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
            self._state = replace(
                self._state,
                ready=False,
                worker_alive=False,
                online=False,
                usable=False,
            )

    def _start_worker(self) -> None:
        self._stop_event.clear()
        self._process = self._context.Process(
            target=run_aero_bus_worker,
            args=(self._config, self._state_queue, self._stop_event),
            name="aero-bus-worker",
            daemon=True,
        )
        self._process.start()
        LOGGER.info(
            "Started read-only AERO BUS worker pid=%s port=%s slave=%s",
            self._process.pid,
            self._config.port,
            self._config.slave_address,
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
