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
class ExtractTachoConfig:
    chip_path: str = "/dev/gpiochip0"
    line_name: str = "GPIO27"
    timeout_seconds: float = 0.25
    averaging_periods: int = 6


class ExtractTachoMonitor:
    """Read-only libgpiod monitor for the validated EXTRACT TACHO channel.

    Failure of this monitor is deliberately isolated from DAC control.  The
    monitor owns only one GPIO input and exposes measurement/health state.
    """

    def __init__(self, config: ExtractTachoConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._gpiod: ModuleType | None = None
        self._line_offset: int | None = None
        self._ready = False
        self._last_error: str | None = None
        self._estimator = TachoEstimator(
            averaging_periods=config.averaging_periods,
            timeout_seconds=config.timeout_seconds,
        )
        self._start_worker()

    def state(self) -> TachoMonitorState:
        with self._lock:
            reading = self._estimator.read(time.monotonic())
            extract = FanTachoState.from_reading(
                line_name=self._config.line_name,
                line_offset=self._line_offset,
                reading=reading,
            )
            thread = self._thread
            return TachoMonitorState(
                chip_path=self._config.chip_path,
                ready=self._ready,
                worker_alive=thread is not None and thread.is_alive(),
                last_error=self._last_error,
                supply=None,
                extract=extract,
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
                name="wvc-extract-tacho",
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
            with gpiod.Chip(self._config.chip_path) as chip:
                line_offset = int(chip.line_offset_from_id(self._config.line_name))

            settings = gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT,
                edge_detection=gpiod.line.Edge.RISING,
                bias=gpiod.line.Bias.DISABLED,
                event_clock=gpiod.line.Clock.MONOTONIC,
            )

            with gpiod.request_lines(
                self._config.chip_path,
                consumer="ventilation-core-extract-tacho",
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
            LOGGER.warning("EXTRACT TACHO monitor stopped: %s", exc)
            with self._lock:
                self._ready = False
                self._last_error = str(exc)
        finally:
            with self._lock:
                self._ready = False
