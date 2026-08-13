from __future__ import annotations

import importlib
import logging
import threading
import time
from dataclasses import dataclass
from types import ModuleType

from ventilation_core.domain.tacho import FanTachoState, TachoEstimator, TachoMonitorState


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TachoMonitorConfig:
    chip_path: str = "/dev/gpiochip0"
    supply_line_name: str | None = None
    extract_line_name: str | None = "GPIO27"
    timeout_seconds: float = 0.25
    averaging_periods: int = 6

    def __post_init__(self) -> None:
        if self.supply_line_name is None and self.extract_line_name is None:
            raise ValueError("At least one TACHO channel must be configured")
        if (
            self.supply_line_name is not None
            and self.extract_line_name is not None
            and self.supply_line_name == self.extract_line_name
        ):
            raise ValueError("SUPPLY and EXTRACT TACHO must use different GPIO lines")
        if self.timeout_seconds <= 0.0:
            raise ValueError("TACHO timeout must be positive")
        if self.averaging_periods < 1:
            raise ValueError("TACHO averaging periods must be at least 1")


class _TachoChannelMonitor:
    """One isolated read-only libgpiod TACHO channel."""

    def __init__(
        self,
        *,
        chip_path: str,
        line_name: str,
        consumer: str,
        timeout_seconds: float,
        averaging_periods: int,
    ) -> None:
        self._chip_path = chip_path
        self._line_name = line_name
        self._consumer = consumer
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._gpiod: ModuleType | None = None
        self._line_offset: int | None = None
        self._ready = False
        self._last_error: str | None = None
        self._estimator = TachoEstimator(
            averaging_periods=averaging_periods,
            timeout_seconds=timeout_seconds,
        )
        self._start_worker()

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._ready

    @property
    def worker_alive(self) -> bool:
        with self._lock:
            thread = self._thread
            return thread is not None and thread.is_alive()

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def state(self) -> FanTachoState:
        with self._lock:
            reading = self._estimator.read(time.monotonic())
            return FanTachoState.from_reading(
                line_name=self._line_name,
                line_offset=self._line_offset,
                reading=reading,
            )

    def health_check(self) -> None:
        with self._lock:
            thread = self._thread
            should_restart = (
                not self._stop_event.is_set()
                and (thread is None or not thread.is_alive())
            )
        if should_restart:
            self._start_worker()

    def close(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            self._ready = False

    def _start_worker(self) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return
            if self._thread is not None and self._thread.is_alive():
                return
            self._ready = False
            self._thread = threading.Thread(
                target=self._run,
                name=self._consumer,
                daemon=True,
            )
            self._thread.start()

    def _load_gpiod(self) -> ModuleType:
        if self._gpiod is None:
            self._gpiod = importlib.import_module("gpiod")
        return self._gpiod

    def _run(self) -> None:
        try:
            gpiod = self._load_gpiod()
            with gpiod.Chip(self._chip_path) as chip:
                line_offset = int(chip.line_offset_from_id(self._line_name))

            settings = gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT,
                edge_detection=gpiod.line.Edge.RISING,
                bias=gpiod.line.Bias.DISABLED,
                event_clock=gpiod.line.Clock.MONOTONIC,
            )

            with gpiod.request_lines(
                self._chip_path,
                consumer=self._consumer,
                config={(line_offset,): settings},
                event_buffer_size=64,
            ) as request:
                with self._lock:
                    self._line_offset = line_offset
                    self._last_error = None
                    self._ready = True
                    self._estimator.reset()

                while not self._stop_event.is_set():
                    if not request.wait_edge_events(0.1):
                        continue
                    for event in request.read_edge_events():
                        if event.line_offset != line_offset:
                            continue
                        timestamp = event.timestamp_ns / 1_000_000_000.0
                        with self._lock:
                            self._estimator.add_edge(timestamp)
        except Exception as exc:
            LOGGER.warning("TACHO monitor %s stopped: %s", self._line_name, exc)
            with self._lock:
                self._ready = False
                self._last_error = str(exc)
        finally:
            with self._lock:
                self._ready = False


class TachoMonitor:
    """Read-only dual-channel TACHO monitor isolated from DAC control.

    SUPPLY and EXTRACT use separate GPIO workers. A failure of either feedback
    channel never changes a DAC setpoint and never creates a ventilation-core
    hardware alarm.
    """

    def __init__(self, config: TachoMonitorConfig) -> None:
        self._config = config
        self._supply = self._build_channel(
            config.supply_line_name,
            consumer="ventilation-core-supply-tacho",
        )
        self._extract = self._build_channel(
            config.extract_line_name,
            consumer="ventilation-core-extract-tacho",
        )

    def _build_channel(
        self,
        line_name: str | None,
        *,
        consumer: str,
    ) -> _TachoChannelMonitor | None:
        if line_name is None:
            return None
        return _TachoChannelMonitor(
            chip_path=self._config.chip_path,
            line_name=line_name,
            consumer=consumer,
            timeout_seconds=self._config.timeout_seconds,
            averaging_periods=self._config.averaging_periods,
        )

    def state(self) -> TachoMonitorState:
        channels = [
            channel
            for channel in (self._supply, self._extract)
            if channel is not None
        ]
        errors: list[str] = []
        if self._supply is not None and self._supply.last_error:
            errors.append(f"SUPPLY: {self._supply.last_error}")
        if self._extract is not None and self._extract.last_error:
            errors.append(f"EXTRACT: {self._extract.last_error}")

        return TachoMonitorState(
            chip_path=self._config.chip_path,
            ready=all(channel.ready for channel in channels),
            worker_alive=all(channel.worker_alive for channel in channels),
            last_error="; ".join(errors) if errors else None,
            supply=None if self._supply is None else self._supply.state(),
            extract=None if self._extract is None else self._extract.state(),
        )

    def health_check(self) -> None:
        for channel in (self._supply, self._extract):
            if channel is not None:
                channel.health_check()

    def close(self) -> None:
        for channel in (self._supply, self._extract):
            if channel is not None:
                channel.close()


@dataclass(frozen=True)
class ExtractTachoConfig:
    """Backward-compatible configuration for the original EXTRACT-only API."""

    chip_path: str = "/dev/gpiochip0"
    line_name: str = "GPIO27"
    timeout_seconds: float = 0.25
    averaging_periods: int = 6


class ExtractTachoMonitor(TachoMonitor):
    """Backward-compatible EXTRACT-only wrapper."""

    def __init__(self, config: ExtractTachoConfig) -> None:
        super().__init__(
            TachoMonitorConfig(
                chip_path=config.chip_path,
                supply_line_name=None,
                extract_line_name=config.line_name,
                timeout_seconds=config.timeout_seconds,
                averaging_periods=config.averaging_periods,
            )
        )
