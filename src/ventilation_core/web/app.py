from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from .client import CoreClient, CoreClientError
from .config import WebUiConfig
from .weather import WeatherError


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


class WeatherProvider(Protocol):
    def get_snapshot(self) -> dict[str, Any]: ...


class WebApplication:
    """Narrow application boundary exposed to the browser.

    The browser never receives a generic ventilation-core command proxy. Only the
    explicitly listed intents below can cross this boundary. ALERTY remain owned
    by ventilation-core; Web V2 only reads them and forwards operator ACK by id.
    Zigbee writes are limited to explicit management intents.
    """

    def __init__(
        self,
        core: CoreClient,
        config: WebUiConfig | None = None,
        weather: WeatherProvider | None = None,
    ) -> None:
        self._core = core
        self._config = config or WebUiConfig()
        self._weather_provider = weather

    def handle(self, method: str, path: str, body: Any = None) -> ApiResponse:
        try:
            if method == "GET" and path == "/api/v1/state":
                return self._state()
            if method == "GET" and path == "/api/v1/zigbee":
                return self._zigbee()
            if method == "GET" and path == "/api/v1/alerts":
                return self._alerts()
            if method == "GET" and path == "/api/v1/config":
                return ApiResponse(200, {"ok": True, "config": self._config.to_public_dict()})
            if method == "GET" and path == "/api/v1/weather":
                return self._weather()
            if method == "GET" and path == "/api/v1/health":
                return self._health()
            if method == "POST" and path == "/api/v1/alerts/ack":
                return self._ack_alert(body)
            if method == "POST" and path == "/api/v1/zigbee/permit-join":
                return self._zigbee_permit_join(body)
            if method == "POST" and path == "/api/v1/zigbee/remove":
                return self._zigbee_remove(body)
            if method == "POST" and path == "/api/v1/zigbee/rename":
                return self._zigbee_rename(body)
            if method == "POST" and path == "/api/v1/zigbee/role":
                return self._zigbee_role(body)
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

    def _zigbee(self) -> ApiResponse:
        response = self._core.request({"command": "status"})
        state = response.get("state")
        if response.get("ok") is not True or not isinstance(state, dict):
            return self._core_rejection(response)
        zigbee = state.get("zigbee")
        if not isinstance(zigbee, dict):
            return ApiResponse(
                503,
                {"ok": False, "error": "Zigbee telemetry is not available from ventilation-core"},
            )
        return ApiResponse(200, {"ok": True, "zigbee": zigbee})

    def _alerts(self) -> ApiResponse:
        response = self._core.request({"command": "alerts", "limit": 200})
        if (
            response.get("ok") is not True
            or not isinstance(response.get("active"), list)
            or not isinstance(response.get("history"), list)
        ):
            return self._core_rejection(response)
        return ApiResponse(200, response)

    def _ack_alert(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        alert_id = data.get("alert_id")
        if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
            raise ValueError("alert_id must be a positive integer")
        return self._command({"command": "ack-alert", "alert_id": alert_id})

    def _zigbee_permit_join(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        seconds = data.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 <= seconds <= 254:
            raise ValueError("seconds must be an integer in range 0..254")
        return self._command({"command": "zigbee-permit-join", "seconds": seconds})

    def _zigbee_remove(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        device_id = data.get("device_id")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string")
        return self._command(
            {"command": "zigbee-remove-device", "device_id": device_id.strip()}
        )

    def _zigbee_rename(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        device_id = data.get("device_id")
        new_name = data.get("new_name")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string")
        if not isinstance(new_name, str) or not new_name.strip():
            raise ValueError("new_name must be a non-empty string")
        return self._command(
            {
                "command": "zigbee-rename-device",
                "device_id": device_id.strip(),
                "new_name": new_name.strip(),
            }
        )

    def _zigbee_role(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        device_id = data.get("device_id")
        role = data.get("role")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string")
        if role not in (None, "supply", "extract"):
            raise ValueError("role must be supply, extract or null")
        return self._command(
            {
                "command": "zigbee-assign-role",
                "device_id": device_id.strip(),
                "role": role,
            }
        )

    def _weather(self) -> ApiResponse:
        if self._weather_provider is None:
            return ApiResponse(
                200,
                {
                    "ok": True,
                    "weather": {
                        "available": False,
                        "configured": False,
                        "error": "weather provider is not configured",
                    },
                },
            )
        try:
            snapshot = self._weather_provider.get_snapshot()
        except WeatherError as exc:
            snapshot = {
                "available": False,
                "configured": True,
                "error": str(exc),
            }
        return ApiResponse(200, {"ok": True, "weather": snapshot})

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
