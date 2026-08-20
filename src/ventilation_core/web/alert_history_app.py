from __future__ import annotations

from typing import Any

from .alert_history import AlertHistoryUnavailable, SqliteAlertHistoryReader
from .app import ApiResponse, WebApplication
from .host_power import HostPowerError


class AlertHistoryWebApplication(WebApplication):
    """WebApplication extension for alert history, SERVICE diagnostics and host power.

    Current/active alert operations still go through ventilation-core. Historical
    browsing is served from a separate read-only view of the same core-owned
    SQLite journal so the browser never downloads the whole multi-year register.
    SERVICE diagnostics are supplied by a separate read-only backend provider and
    never expose a generic shell or control-command proxy to the browser.

    CM5 host power is a deliberately separate, narrow privileged boundary. The
    browser can request only the explicit ``shutdown`` or ``restart`` operations;
    the WebUI never receives a generic host-command or shell proxy.
    """

    HOST_POWER_ACTIONS = ("shutdown", "restart")

    def __init__(
        self,
        *args: Any,
        alert_history: SqliteAlertHistoryReader | None = None,
        service_status: Any | None = None,
        host_power: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._alert_history = alert_history
        self._service_status_provider = service_status
        self._host_power = host_power

    def handle(self, method: str, path: str, body: Any = None) -> ApiResponse:
        if method == "GET" and path == "/api/v1/service/status":
            return self._service_status()

        if method == "POST" and path == "/api/v1/system/power":
            try:
                return self._host_power_action(body)
            except ValueError as exc:
                return ApiResponse(400, {"ok": False, "error": str(exc)})
            except HostPowerError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "POST" and path == "/api/v1/history/alerts/days":
            try:
                return self._alert_history_days(body)
            except ValueError as exc:
                return ApiResponse(400, {"ok": False, "error": str(exc)})
            except AlertHistoryUnavailable as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "POST" and path == "/api/v1/history/alerts/day":
            try:
                return self._alert_history_day(body)
            except ValueError as exc:
                return ApiResponse(400, {"ok": False, "error": str(exc)})
            except AlertHistoryUnavailable as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        return super().handle(method, path, body)

    def _service_status(self) -> ApiResponse:
        provider = self._service_status_provider
        if provider is None:
            return ApiResponse(
                200,
                {
                    "ok": True,
                    "service": {
                        "available": False,
                        "configured": False,
                        "read_only": True,
                        "error": "service diagnostics provider is not configured",
                    },
                },
            )
        try:
            snapshot = provider.get_snapshot()
        except Exception as exc:
            return ApiResponse(
                200,
                {
                    "ok": True,
                    "service": {
                        "available": False,
                        "configured": True,
                        "read_only": True,
                        "error": str(exc),
                    },
                },
            )
        return ApiResponse(200, {"ok": True, "service": snapshot})

    def _host_power_action(self, body: Any) -> ApiResponse:
        client = self._host_power
        if client is None:
            return ApiResponse(503, {"ok": False, "error": "host power agent is not configured"})

        data = self._require_object(body)
        if set(data) != {"action"}:
            raise ValueError("request must contain only action")
        action = data.get("action")
        if action not in self.HOST_POWER_ACTIONS:
            raise ValueError("action must be shutdown or restart")

        response = client.request(str(action))
        if response.get("ok") is not True or response.get("accepted") is not True:
            return ApiResponse(
                503,
                {
                    "ok": False,
                    "error": response.get("error") or "host power agent rejected request",
                },
            )
        if response.get("action") != action:
            return ApiResponse(502, {"ok": False, "error": "host power agent returned mismatched action"})

        return ApiResponse(
            202,
            {
                "ok": True,
                "accepted": True,
                "action": action,
            },
        )

    def _alert_history_days(self, body: Any) -> ApiResponse:
        provider = self._alert_history
        if provider is None:
            return ApiResponse(
                503,
                {"ok": False, "error": "alert history is not configured"},
            )
        data = self._require_object(body)
        timezone_name = data.get("timezone")
        before_day = data.get("before_day")
        window_days = data.get(
            "window_days",
            provider.DEFAULT_INDEX_WINDOW_DAYS,
        )
        payload = provider.day_index(
            timezone_name=timezone_name,
            before_day=before_day,
            window_days=window_days,
        )
        return ApiResponse(200, {"ok": True, "alert_history": payload})

    def _alert_history_day(self, body: Any) -> ApiResponse:
        provider = self._alert_history
        if provider is None:
            return ApiResponse(
                503,
                {"ok": False, "error": "alert history is not configured"},
            )
        data = self._require_object(body)
        cursor = data.get("cursor")
        before_cleared_at = None
        before_alert_id = None
        if cursor is not None:
            if not isinstance(cursor, dict):
                raise ValueError("cursor must be a JSON object or null")
            before_cleared_at = cursor.get("before_cleared_at")
            before_alert_id = cursor.get("before_alert_id")

        payload = provider.query_day(
            day=data.get("day"),
            timezone_name=data.get("timezone"),
            limit=data.get("limit", provider.DEFAULT_DAY_PAGE_SIZE),
            before_cleared_at=before_cleared_at,
            before_alert_id=before_alert_id,
        )
        return ApiResponse(200, {"ok": True, "alert_history": payload})
