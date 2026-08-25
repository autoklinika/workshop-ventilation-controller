from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ventilation_core.web.client import CoreClientError

from .client import ReadOnlyCore


@dataclass(frozen=True)
class HaResponse:
    status: int
    payload: dict[str, Any]


class HaReadOnlyApplication:
    """Minimal read-only HTTP application for Home Assistant.

    This boundary intentionally exposes no acknowledgement, schedule, Zigbee,
    fan, AERO, host-power or generic core command endpoint.
    """

    def __init__(self, core: ReadOnlyCore) -> None:
        self._core = core

    def handle(self, method: str, path: str) -> HaResponse:
        if method != "GET":
            return HaResponse(405, {"ok": False, "error": "Method not allowed; HA API is read-only"})
        try:
            if path == "/api/ha/v1/state":
                return HaResponse(200, self._core.status())
            if path == "/api/ha/v1/alerts":
                return HaResponse(200, self._core.alerts(limit=200))
            if path == "/api/ha/v1/health":
                return self._health()
            return HaResponse(404, {"ok": False, "error": "Not found"})
        except (CoreClientError, OSError, TimeoutError) as exc:
            return HaResponse(503, {"ok": False, "error": str(exc)})

    def _health(self) -> HaResponse:
        try:
            self._core.status()
        except (CoreClientError, OSError, TimeoutError) as exc:
            return HaResponse(
                200,
                {
                    "ok": True,
                    "ha_api": "ok",
                    "read_only": True,
                    "core_available": False,
                    "core_error": str(exc),
                },
            )
        return HaResponse(
            200,
            {
                "ok": True,
                "ha_api": "ok",
                "read_only": True,
                "core_available": True,
            },
        )
