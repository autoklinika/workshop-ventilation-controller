from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from ventilation_core.application.service import VentilationService
from ventilation_core.domain.aero_control import AeroControlCommand


LOGGER = logging.getLogger(__name__)


class CoreServer:
    def __init__(
        self,
        service: VentilationService,
        socket_path: Path,
        health_interval_seconds: float,
    ) -> None:
        self._service = service
        self._socket_path = socket_path
        self._health_interval = health_interval_seconds
        self._shutdown = asyncio.Event()
        self._server: asyncio.AbstractServer | None = None

    async def run(self) -> None:
        health_task: asyncio.Task[None] | None = None
        try:
            self._prepare_socket_path()
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=str(self._socket_path),
            )
            os.chmod(self._socket_path, 0o660)
            health_task = asyncio.create_task(self._health_monitor())
            LOGGER.info("ventilation-core listening on %s", self._socket_path)
            await self._shutdown.wait()
        finally:
            if health_task is not None:
                health_task.cancel()
                await asyncio.gather(health_task, return_exceptions=True)
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
            try:
                await asyncio.to_thread(self._service.close)
            finally:
                self._remove_socket()

    def request_shutdown(self) -> None:
        self._shutdown.set()

    def _prepare_socket_path(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_socket()

    def _remove_socket(self) -> None:
        try:
            self._socket_path.unlink()
        except FileNotFoundError:
            pass

    async def _health_monitor(self) -> None:
        while True:
            await asyncio.sleep(self._health_interval)
            try:
                await asyncio.to_thread(self._service.health_check)
            except Exception:
                LOGGER.exception("Core hardware health check failed")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
            request = json.loads(raw.decode("utf-8"))
            response = await self._dispatch(request)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}

        payload = (json.dumps(response) + "\n").encode("utf-8")
        try:
            writer.write(payload)
            await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.debug("Unix socket client disconnected before response delivery completed")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if command == "status":
            state = self._service.state()
            return {"ok": True, "state": state.to_dict()}
        if command == "alerts":
            limit = request.get("limit", 200)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
                raise ValueError("Alert history limit must be an integer in range 1..1000")
            history_method = getattr(self._service, "alert_history", None)
            if history_method is None:
                raise RuntimeError("Alert history is not configured")
            history = await asyncio.to_thread(history_method, limit)
            state = self._service.state()
            return {
                "ok": True,
                "active": [alarm.to_dict() for alarm in state.active_alarms],
                "history": [record.to_dict() for record in history],
            }
        if command == "ack-alert":
            alert_id = request.get("alert_id")
            if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
                raise ValueError("alert_id must be a positive integer")
            acknowledge_method = getattr(self._service, "acknowledge_alert", None)
            if acknowledge_method is None:
                raise RuntimeError("Alert acknowledgement is not configured")
            record = await asyncio.to_thread(acknowledge_method, alert_id)
            return {
                "ok": True,
                "alert": record.to_dict(),
                "state": self._service.state().to_dict(),
            }
        if command == "sensors":
            sensor_bus = self._service.state().sensor_bus
            return {
                "ok": True,
                "sensor_bus": None if sensor_bus is None else sensor_bus.to_dict(),
            }
        if command == "aero":
            aero_bus = self._service.state().aero_bus
            return {
                "ok": True,
                "aero_bus": None if aero_bus is None else aero_bus.to_dict(),
            }
        if command == "aero-speed":
            speed = request["speed"]
            if isinstance(speed, bool) or not isinstance(speed, int):
                raise ValueError("AERO speed must be an integer 0..3")
            result = await asyncio.to_thread(
                self._service.control_aero,
                AeroControlCommand.set_speed(speed),
            )
            return {"ok": result.succeeded, "aero_control": result.to_dict()}
        if command == "aero-airing":
            enabled = request["enabled"]
            if not isinstance(enabled, bool):
                raise ValueError("AERO airing state must be boolean")
            result = await asyncio.to_thread(
                self._service.control_aero,
                AeroControlCommand.set_airing(enabled),
            )
            return {"ok": result.succeeded, "aero_control": result.to_dict()}
        if command == "set":
            state = await asyncio.to_thread(
                self._service.set_manual,
                float(request["supply_voltage"]),
                float(request["extract_voltage"]),
            )
        elif command == "stop":
            state = await asyncio.to_thread(self._service.stop)
        elif command == "shutdown":
            state = await asyncio.to_thread(self._service.stop)
            self.request_shutdown()
        else:
            raise ValueError(f"Unsupported command: {command}")
        return {"ok": True, "state": state.to_dict()}
