from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import uuid
from typing import Any

from ventilation_core.domain.models import FanSetpoints

from .hardware_worker import hardware_worker_main


class HardwareWorkerError(RuntimeError):
    pass


class ProcessIsolatedActuator:
    """Application-side proxy for the isolated I2C hardware worker process."""

    def __init__(self, bus: int, address: int, timeout_seconds: float = 3.0) -> None:
        self._bus = bus
        self._address = address
        self._timeout = timeout_seconds
        self._context = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._process: mp.Process | None = None
        self._command_queue: Any = None
        self._response_queue: Any = None
        self._ready = False
        self._last_error: str | None = None
        self._start_worker()

    @property
    def ready(self) -> bool:
        return self._ready and self._process is not None and self._process.is_alive()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _start_worker(self) -> None:
        self._command_queue = self._context.Queue()
        self._response_queue = self._context.Queue()
        self._process = self._context.Process(
            target=hardware_worker_main,
            name="ventilation-hardware-worker",
            args=(self._bus, self._address, self._command_queue, self._response_queue),
            daemon=True,
        )
        self._process.start()
        try:
            response = self._response_queue.get(timeout=self._timeout)
        except queue.Empty as exc:
            self._terminate_worker()
            raise HardwareWorkerError("Hardware worker startup timed out") from exc
        if response.get("request_id") != "__startup__" or not response.get("ok"):
            self._terminate_worker()
            raise HardwareWorkerError(response.get("error", "Hardware worker failed to start"))
        self._ready = bool(response.get("hardware_ready"))
        self._last_error = response.get("error")

    def _terminate_worker(self) -> None:
        process = self._process
        self._ready = False
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        self._process = None

    def _ensure_worker(self) -> bool:
        if self._process is None or not self._process.is_alive():
            self._ready = False
            self._start_worker()
            return True
        return False

    def _request(self, command: str, **payload: Any) -> None:
        with self._lock:
            worker_restarted = self._ensure_worker()
            if worker_restarted and command not in ("recover", "shutdown"):
                self._ready = False
                self._last_error = (
                    "Hardware worker restarted; safe recovery is required before commands"
                )
                raise HardwareWorkerError(self._last_error)
            request_id = uuid.uuid4().hex
            self._command_queue.put(
                {"request_id": request_id, "command": command, **payload}
            )
            try:
                response = self._response_queue.get(timeout=self._timeout)
            except queue.Empty as exc:
                self._last_error = f"Hardware command timed out: {command}"
                self._terminate_worker()
                raise HardwareWorkerError(self._last_error) from exc
            if response.get("request_id") != request_id:
                self._last_error = "Hardware response correlation failed"
                self._terminate_worker()
                raise HardwareWorkerError(self._last_error)
            if not response.get("ok"):
                self._ready = False
                self._last_error = response.get("error", "Hardware command failed")
                raise HardwareWorkerError(self._last_error)
            self._ready = True
            self._last_error = None

    def apply(self, setpoints: FanSetpoints) -> None:
        self._request(
            "apply",
            supply_voltage=setpoints.supply_voltage,
            extract_voltage=setpoints.extract_voltage,
        )

    def stop_all(self) -> None:
        self._request("stop")

    def health_check(self) -> None:
        self._request("health")

    def recover(self) -> None:
        self._request("recover")

    def close(self) -> None:
        with self._lock:
            if self._process is None:
                return
            if self._process.is_alive():
                try:
                    self._request("shutdown")
                except Exception:
                    pass
                self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)
            self._ready = False
            self._process = None
