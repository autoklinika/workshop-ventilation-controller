from __future__ import annotations

import asyncio
from typing import Any

from ventilation_core.runtime.server import CoreServer


class ControlEngineCoreServer(CoreServer):
    """CoreServer extension for non-actuating Control Engine state only."""

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

        if command == "control-engine-operator":
            method = getattr(self._service, "control_engine_operator_state", None)
            if method is None:
                raise RuntimeError("Control Engine operator runtime is not configured")
            operator = await asyncio.to_thread(method)
            return {"ok": True, "operator": operator}

        if command == "control-engine-operator-replace":
            raw_operator = request.get("operator")
            if not isinstance(raw_operator, dict):
                raise ValueError("Control Engine operator intent must be a JSON object")
            method = getattr(self._service, "replace_control_engine_operator_intent", None)
            if method is None:
                raise RuntimeError("Control Engine operator runtime is not configured")
            operator = await asyncio.to_thread(method, raw_operator)
            return {
                "ok": True,
                "operator": operator,
                "state": self._service.state().to_dict(),
            }

        return await super()._dispatch(request)
