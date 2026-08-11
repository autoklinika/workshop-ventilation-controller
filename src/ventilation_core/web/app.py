from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .client import CoreClient, CoreClientError
from .config import WebUiConfig


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


class WebApplication:
    """Narrow application boundary exposed to the browser.

    The browser never receives a generic ventilation-core command proxy. Only the
    explicitly listed manual-control intents below can cross this boundary.
    """

    def __init__(self, core: CoreClient, config: WebUiConfig | None = None) -> None:
        self._core = core
        self._config = config or WebUiConfig()

    def handle(self, method: str, path: str, body: Any = None) -> ApiResponse:
        try:
            if method == "GET" and path == "/api/v1/state":
                return self._state()
            if method == "GET" and path == "/api/v1/config":
                return ApiResponse(200, {"ok": True, "config": self._config.to_public_dict()})
            if method == "GET" and path == "/api/v1/health":
                return self._health()
            if method == "POST" and path == "/api/v1/manual/fans":
                return self._fans(body)
            if method == "POST" and path == "/api/v1/manual/stop":
                return self._command({"command": "stop"})
            if method == "POST" and path == "/api/v1/manual/aero/speed":
                return self._aero_speed(body)
            if method == "POST" and path == "/api/v1/manual/aero/airing":
                return self._aero_airing(body)
            return ApiResponse(404, {"ok": False, "error": "Not found"})
        except ValueError as exc:
            return ApiResponse(400, {"ok": False, "error": str(exc)})
        except CoreClientError as exc:
            return ApiResponse(503, {"ok": False, "error": str(exc)})

    def _state(self) -> ApiResponse:
        response = self._core.request({"command": "status"})
        if response.get("ok") is not True or not isinstance(response.get("state"), dict):
            return self._core_rejection(response)
        return ApiResponse(200, response)

    def _health(self) -> ApiResponse:
        try:
            response = self._core.request({"command": "status"})
        except CoreClientError as exc:
            return ApiResponse(
                200,
                {"ok": True, "web": "ok", "core_available": False, "core_error": str(exc)},
            )
        return ApiResponse(
            200,
            {
                "ok": True,
                "web": "ok",
                "core_available": response.get("ok") is True,
            },
        )

    def _fans(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        supply = self._require_voltage(data, "supply_voltage")
        extract = self._require_voltage(data, "extract_voltage")
        return self._command(
            {
                "command": "set",
                "supply_voltage": supply,
                "extract_voltage": extract,
            }
        )

    def _aero_speed(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        speed = data.get("speed")
        if isinstance(speed, bool) or not isinstance(speed, int) or speed not in (0, 1, 2, 3):
            raise ValueError("AERO speed must be an integer 0..3")
        return self._command({"command": "aero-speed", "speed": speed})

    def _aero_airing(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("AERO airing state must be boolean")
        return self._command({"command": "aero-airing", "enabled": enabled})

    def _command(self, payload: dict[str, Any]) -> ApiResponse:
        response = self._core.request(payload)
        if response.get("ok") is True:
            return ApiResponse(200, response)
        return self._core_rejection(response)

    @staticmethod
    def _core_rejection(response: dict[str, Any]) -> ApiResponse:
        error = response.get("error")
        if not isinstance(error, str) or not error:
            error = "ventilation-core rejected the command"
        return ApiResponse(409, {**response, "ok": False, "error": error})

    @staticmethod
    def _require_object(body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ValueError("JSON object body required")
        return body

    @staticmethod
    def _require_voltage(data: dict[str, Any], key: str) -> float:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{key} must be finite")
        if numeric != 0.0 and not 1.0 <= numeric <= 10.0:
            raise ValueError(f"{key} must be 0.0 V or within 1.0..10.0 V")
        return numeric
