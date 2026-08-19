from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from ventilation_core.telemetry.history import TelemetryHistoryUnavailable

from .advisory import AdvisoryError
from .client import CoreClient, CoreClientError
from .config import WebUiConfig
from .weather import WeatherError


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


class WeatherProvider(Protocol):
    def get_snapshot(self) -> dict[str, Any]: ...


class AdvisoryProvider(Protocol):
    def get_snapshot(self) -> dict[str, Any]: ...


class HistoryProvider(Protocol):
    def status(self) -> Any: ...

    def query(
        self,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        limit: int = 720,
        resolution: str = "raw",
    ) -> list[dict[str, Any]]: ...


class WebApplication:
    """Narrow browser boundary for manual control, alerts, schedule, history and Zigbee.

    The browser never receives a generic ventilation-core command proxy and never
    opens SQLite or MQTT directly. Schedule evaluation, SHADOW and Zigbee state are
    authoritative in ventilation-core. Destructive Zigbee removal uses core-owned
    two-step confirmation.
    """

    SCHEDULE_ZONES = ("zone-1", "zone-2")
    SCHEDULE_EXPECTATIONS = ("OCCUPIED_EXPECTED", "UNOCCUPIED_EXPECTED")
    MAX_SCHEDULE_WINDOWS_PER_ZONE = 64

    def __init__(
        self,
        core: CoreClient,
        config: WebUiConfig | None = None,
        weather: WeatherProvider | None = None,
        history: HistoryProvider | None = None,
        advisory: AdvisoryProvider | None = None,
    ) -> None:
        self._core = core
        self._config = config or WebUiConfig()
        self._weather_provider = weather
        self._history_provider = history
        self._advisory_provider = advisory

    def handle(self, method: str, path: str, body: Any = None) -> ApiResponse:
        try:
            if method == "GET" and path == "/api/v1/state":
                return self._state()
            if method == "GET" and path == "/api/v1/zigbee":
                return self._zigbee()
            if method == "GET" and path == "/api/v1/zigbee/removal-confirmation":
                return self._zigbee_removal_confirmation()
            if method == "GET" and path == "/api/v1/alerts":
                return self._alerts()
            if method == "GET" and path == "/api/v1/schedule":
                return self._schedule()
            if method == "GET" and path == "/api/v1/config":
                return ApiResponse(200, {"ok": True, "config": self._config.to_public_dict()})
            if method == "GET" and path == "/api/v1/weather":
                return self._weather()
            if method == "GET" and path == "/api/v1/ai/advisory":
                return self._advisory()
            if method == "GET" and path == "/api/v1/history/status":
                return self._history_status()
            if method == "GET" and path == "/api/v1/health":
                return self._health()
            if method == "POST" and path == "/api/v1/history/query":
                return self._history_query(body)
            if method == "POST" and path == "/api/v1/alerts/ack":
                return self._ack_alert(body)
            if method == "POST" and path == "/api/v1/schedule/zone":
                return self._schedule_replace(body)
            if method == "POST" and path == "/api/v1/zigbee/permit-join":
                return self._zigbee_permit_join(body)
            if method == "POST" and path == "/api/v1/zigbee/pairing/ack":
                return self._zigbee_pairing_ack(body)
            if method == "POST" and path == "/api/v1/zigbee/remove":
                return self._zigbee_remove(body)
            if method == "POST" and path == "/api/v1/zigbee/remove-confirmation":
                return self._zigbee_remove_confirmation(body)
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
        except TelemetryHistoryUnavailable as exc:
            return ApiResponse(503, {"ok": False, "error": str(exc)})
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
            return ApiResponse(503, {"ok": False, "error": "Zigbee telemetry is not available from ventilation-core"})
        return ApiResponse(200, {"ok": True, "zigbee": zigbee})

    def _zigbee_removal_confirmation(self) -> ApiResponse:
        response = self._core.request({"command": "zigbee-removal-confirmation-state"})
        if response.get("ok") is not True:
            return self._core_rejection(response)
        confirmation = response.get("confirmation")
        if confirmation is not None and not isinstance(confirmation, dict):
            return ApiResponse(502, {"ok": False, "error": "Invalid confirmation state from core"})
        return ApiResponse(200, {"ok": True, "confirmation": confirmation})

    def _alerts(self) -> ApiResponse:
        response = self._core.request({"command": "alerts", "limit": 200})
        if response.get("ok") is not True or not isinstance(response.get("active"), list) or not isinstance(response.get("history"), list):
            return self._core_rejection(response)
        return ApiResponse(200, response)

    def _schedule(self) -> ApiResponse:
        response = self._core.request({"command": "schedule"})
        if response.get("ok") is not True or not isinstance(response.get("schedule"), dict):
            return self._core_rejection(response)
        return ApiResponse(200, response)

    def _schedule_replace(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        zone = data.get("zone")
        if zone not in self.SCHEDULE_ZONES:
            raise ValueError("zone must be one of: zone-1, zone-2")
        windows = data.get("windows")
        if not isinstance(windows, list):
            raise ValueError("windows must be a JSON list")
        if len(windows) > self.MAX_SCHEDULE_WINDOWS_PER_ZONE:
            raise ValueError(f"windows may contain at most {self.MAX_SCHEDULE_WINDOWS_PER_ZONE} entries")
        sanitized = [self._sanitize_schedule_window(window) for window in windows]
        return self._command({"command": "schedule-replace", "zone": zone, "windows": sanitized})

    def _history_status(self) -> ApiResponse:
        provider = self._history_provider
        if provider is None:
            return ApiResponse(200, {"ok": True, "history": {"available": False, "configured": False}})
        status = provider.status()
        payload = status.to_dict() if hasattr(status, "to_dict") else dict(status)
        payload["configured"] = True
        return ApiResponse(200, {"ok": True, "history": payload})

    def _history_query(self, body: Any) -> ApiResponse:
        provider = self._history_provider
        if provider is None:
            return ApiResponse(503, {"ok": False, "error": "local history is not configured"})
        data = self._require_object(body)
        start_at = data.get("start_at")
        end_at = data.get("end_at")
        limit = data.get("limit", 720)
        resolution = data.get("resolution", "raw")
        samples = provider.query(start_at=start_at, end_at=end_at, limit=limit, resolution=resolution)
        return ApiResponse(200, {"ok": True, "resolution": resolution, "count": len(samples), "samples": samples})

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

    def _zigbee_pairing_ack(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        ieee_address = data.get("ieee_address")
        if not isinstance(ieee_address, str) or not ieee_address.strip():
            raise ValueError("ieee_address must be a non-empty string")
        return self._command({"command": "zigbee-ack-pairing", "ieee_address": ieee_address.strip()})

    def _zigbee_remove(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        device_id = data.get("device_id")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string")
        return self._command({"command": "zigbee-request-remove-device", "device_id": device_id.strip()})

    def _zigbee_remove_confirmation(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        confirmation_id = data.get("confirmation_id")
        confirmed = data.get("confirmed")
        if not isinstance(confirmation_id, str) or not confirmation_id.strip():
            raise ValueError("confirmation_id must be a non-empty string")
        if not isinstance(confirmed, bool):
            raise ValueError("confirmed must be boolean")
        return self._command({"command": "zigbee-resolve-remove-device", "confirmation_id": confirmation_id.strip(), "confirmed": confirmed})

    def _zigbee_rename(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        device_id = data.get("device_id")
        new_name = data.get("new_name")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string")
        if not isinstance(new_name, str) or not new_name.strip():
            raise ValueError("new_name must be a non-empty string")
        return self._command({"command": "zigbee-rename-device", "device_id": device_id.strip(), "new_name": new_name.strip()})

    def _zigbee_role(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        device_id = data.get("device_id")
        role = data.get("role")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string")
        if role not in (None, "supply", "extract", "other"):
            raise ValueError("role must be supply, extract, other or null")
        return self._command({"command": "zigbee-assign-role", "device_id": device_id.strip(), "role": role})

    def _weather(self) -> ApiResponse:
        if self._weather_provider is None:
            return ApiResponse(200, {"ok": True, "weather": {"available": False, "configured": False, "error": "weather provider is not configured"}})
        try:
            snapshot = self._weather_provider.get_snapshot()
        except WeatherError as exc:
            snapshot = {"available": False, "configured": True, "error": str(exc)}
        return ApiResponse(200, {"ok": True, "weather": snapshot})

    def _advisory(self) -> ApiResponse:
        if self._advisory_provider is None:
            return ApiResponse(
                200,
                {
                    "ok": True,
                    "advisory": {
                        "available": False,
                        "configured": False,
                        "source": "local-cache",
                        "stale": True,
                        "fresh": False,
                    },
                },
            )

        try:
            snapshot = self._advisory_provider.get_snapshot()
        except AdvisoryError as exc:
            snapshot = {
                "available": False,
                "configured": True,
                "source": "local-cache",
                "stale": True,
                "fresh": False,
                "error": str(exc),
            }

        return ApiResponse(200, {"ok": True, "advisory": snapshot})

    def _health(self) -> ApiResponse:
        try:
            response = self._core.request({"command": "status"})
        except CoreClientError as exc:
            return ApiResponse(200, {"ok": True, "web": "ok", "core_available": False, "core_error": str(exc)})
        return ApiResponse(200, {"ok": True, "web": "ok", "core_available": response.get("ok") is True})

    def _fans(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        supply = self._require_voltage(data, "supply_voltage")
        extract = self._require_voltage(data, "extract_voltage")
        return self._command({"command": "set", "supply_voltage": supply, "extract_voltage": extract})

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

    @classmethod
    def _sanitize_schedule_window(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("each schedule window must be a JSON object")
        allowed = {"weekday", "start_local", "end_local", "expectation", "enabled", "label"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unsupported schedule window fields: {sorted(unknown)}")
        weekday = value.get("weekday")
        if isinstance(weekday, bool) or not isinstance(weekday, int) or not 1 <= weekday <= 7:
            raise ValueError("weekday must be an integer in ISO range 1..7")
        start_local = value.get("start_local")
        end_local = value.get("end_local")
        if not isinstance(start_local, str) or not isinstance(end_local, str):
            raise ValueError("start_local and end_local must be HH:MM text")
        expectation = value.get("expectation", "OCCUPIED_EXPECTED")
        if expectation not in cls.SCHEDULE_EXPECTATIONS:
            raise ValueError("unsupported schedule expectation")
        enabled = value.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        label = value.get("label", "")
        if not isinstance(label, str) or len(label) > 80:
            raise ValueError("label must be text up to 80 characters")
        return {"weekday": weekday, "start_local": start_local, "end_local": end_local, "expectation": expectation, "enabled": enabled, "label": label}

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
