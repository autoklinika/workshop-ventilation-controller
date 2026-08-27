from __future__ import annotations

from typing import Any

from ventilation_core.domain.control_engine_config import ControlEngineConfig

from .alert_history_app import AlertHistoryWebApplication
from .app import ApiResponse
from .client import CoreClientError


class ControlEngineWebApplication(AlertHistoryWebApplication):
    """WebUI extension for Control Engine SHADOW configuration.

    The browser receives no generic core proxy and no actuation-enable endpoint.
    POST accepts a complete, strictly validated configuration and forwards only the
    fixed ``control-engine-replace`` command to ventilation-core.
    """

    def handle(self, method: str, path: str, body: Any = None) -> ApiResponse:
        if method == "GET" and path == "/api/v1/control-engine":
            try:
                return self._control_engine()
            except CoreClientError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "POST" and path == "/api/v1/control-engine":
            try:
                return self._control_engine_replace(body)
            except ValueError as exc:
                return ApiResponse(400, {"ok": False, "error": str(exc)})
            except CoreClientError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        return super().handle(method, path, body)

    def _control_engine(self) -> ApiResponse:
        response = self._core.request({"command": "control-engine"})
        configuration = response.get("control_engine")
        if response.get("ok") is not True or not isinstance(configuration, dict):
            return self._core_rejection(response)
        if configuration.get("actuation_supported") is not False:
            return ApiResponse(
                502,
                {
                    "ok": False,
                    "error": "Invalid Control Engine safety contract from ventilation-core",
                },
            )
        return ApiResponse(200, response)

    def _control_engine_replace(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        if set(data) != {"config"}:
            raise ValueError("Control Engine update accepts only the config field")
        raw_config = data.get("config")
        if not isinstance(raw_config, dict):
            raise ValueError("config must be a JSON object")

        # Defense in depth at the browser boundary. Core validates the same contract
        # authoritatively before persistence.
        sanitized = ControlEngineConfig.from_dict(raw_config).to_dict()
        response = self._core.request(
            {"command": "control-engine-replace", "config": sanitized}
        )
        configuration = response.get("control_engine")
        if response.get("ok") is not True or not isinstance(configuration, dict):
            return self._core_rejection(response)
        if configuration.get("actuation_supported") is not False:
            return ApiResponse(
                502,
                {
                    "ok": False,
                    "error": "Invalid Control Engine safety contract from ventilation-core",
                },
            )
        return ApiResponse(200, response)
