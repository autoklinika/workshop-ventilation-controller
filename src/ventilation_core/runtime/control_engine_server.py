from __future__ import annotations

import asyncio
from typing import Any

from ventilation_core.runtime.server import CoreServer


class ControlEngineCoreServer(CoreServer):
    """CoreServer extension for non-actuating Control Engine configuration only."""

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if command == "control-engine":
            method = getattr(self._service, "control_engine_configuration", None)
            if method is None:
                raise RuntimeError("Persistent Control Engine configuration is not configured")
            configuration = await asyncio.to_thread(method)
            return {"ok": True, "control_engine": configuration}

        if command == "control-engine-replace":
            raw_config = request.get("config")
            if not isinstance(raw_config, dict):
                raise ValueError("Control Engine config must be a JSON object")
            method = getattr(self._service, "replace_control_engine_configuration", None)
            if method is None:
                raise RuntimeError("Persistent Control Engine configuration is not configured")
            configuration = await asyncio.to_thread(method, raw_config)
            return {
                "ok": True,
                "control_engine": configuration,
                "state": self._service.state().to_dict(),
            }

        return await super()._dispatch(request)
