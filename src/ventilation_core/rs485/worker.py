from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import uuid
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

from .serial_transport import PySerialModbusTransport, SerialSettings


class RS485WorkerError(RuntimeError):
    pass


def rs485_worker_main(
    settings: SerialSettings,
    command_queue: Queue,
    response_queue: Queue,
) -> None:
    transport: PySerialModbusTransport | None = None
    try:
        transport = PySerialModbusTransport(settings)
        response_queue.put(
            {
                "request_id": "__startup__",
                "ok": True,
                "port": settings.port,
            }
        )
        while True:
            request = command_queue.get()
            request_id = str(request["request_id"])
            command = str(request["command"])
            try:
                if command == "transact":
                    response = transport.transact(bytes.fromhex(request["frame_hex"]))
                    response_queue.put(
                        {
                            "request_id": request_id,
                            "ok": True,
                            "frame_hex": response.hex(),
                        }
                    )
                elif command == "raw_write":
                    written = transport.write_raw(bytes.fromhex(request["frame_hex"]))
                    response_queue.put(
                        {
                            "request_id": request_id,
                            "ok": True,
                            "written": written,
                        }
                    )
                elif command == "raw_read":
                    response = transport.read_exact(int(request["size"]))
                    response_queue.put(
                        {
                            "request_id": request_id,
                            "ok": True,
                            "frame_hex": response.hex(),
                        }
                    )
                elif command == "ping":
                    response_queue.put({"request_id": request_id, "ok": True})
                elif command == "shutdown":
                    response_queue.put({"request_id": request_id, "ok": True})
                    break
                else:
                    raise ValueError(f"Unsupported RS-485 command: {command}")
            except Exception as exc:
                response_queue.put(
                    {"request_id": request_id, "ok": False, "error": str(exc)}
                )
    except Exception as exc:
        response_queue.put(
            {"request_id": "__startup__", "ok": False, "error": str(exc)}
        )
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass


class ProcessRS485Master:
    """Application-side proxy for one dedicated RS-485 serial owner process.

    Each instance owns exactly one UART/serial port. Multiple instances may run
    concurrently, which allows separate DFR0845 adapters to serve independent
    RS-485 buses without sharing file descriptors or command queues.
    """

    def __init__(self, settings: SerialSettings, timeout_seconds: float = 3.0) -> None:
        self._settings = settings
        self._timeout = timeout_seconds
        self._context = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._command_queue: Any = self._context.Queue()
        self._response_queue: Any = self._context.Queue()
        port_name = Path(settings.port).name.replace(" ", "-") or "port"
        self._process = self._context.Process(
            target=rs485_worker_main,
            name=f"ventilation-rs485-{port_name}",
            args=(settings, self._command_queue, self._response_queue),
            daemon=True,
        )
        self._process.start()
        try:
            response = self._response_queue.get(timeout=self._timeout)
        except queue.Empty as exc:
            self._terminate()
            raise RS485WorkerError("RS-485 worker startup timed out") from exc
        if response.get("request_id") != "__startup__" or not response.get("ok"):
            self._terminate()
            raise RS485WorkerError(
                response.get("error", "RS-485 worker failed to start")
            )

    @property
    def port(self) -> str:
        return self._settings.port

    @property
    def ready(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def _terminate(self) -> None:
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
        self._process = None

    def _request(self, command: str, **payload: Any) -> dict[str, Any]:
        with self._lock:
            if not self.ready:
                raise RS485WorkerError("RS-485 worker is not running")
            request_id = uuid.uuid4().hex
            self._command_queue.put(
                {"request_id": request_id, "command": command, **payload}
            )
            try:
                response = self._response_queue.get(timeout=self._timeout)
            except queue.Empty as exc:
                self._terminate()
                raise RS485WorkerError(
                    f"RS-485 worker command timed out: {command}"
                ) from exc
            if response.get("request_id") != request_id:
                self._terminate()
                raise RS485WorkerError("RS-485 response correlation failed")
            if not response.get("ok"):
                raise RS485WorkerError(response.get("error", "RS-485 command failed"))
            return response

    def ping(self) -> None:
        self._request("ping")

    def write_raw(self, frame: bytes) -> int:
        response = self._request("raw_write", frame_hex=frame.hex())
        return int(response["written"])

    def read_exact(self, size: int) -> bytes:
        response = self._request("raw_read", size=int(size))
        return bytes.fromhex(response["frame_hex"])

    def transact(self, frame: bytes) -> bytes:
        response = self._request("transact", frame_hex=frame.hex())
        return bytes.fromhex(response["frame_hex"])

    def close(self) -> None:
        with self._lock:
            if not self.ready:
                self._process = None
                return
            try:
                self._request("shutdown")
            finally:
                if self._process is not None:
                    self._process.join(timeout=1.0)
                if self.ready:
                    self._terminate()
                self._process = None
