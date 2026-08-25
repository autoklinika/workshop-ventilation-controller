from __future__ import annotations

from typing import Any, Protocol

from ventilation_core.web.client import CoreClient, CoreClientError


class ReadOnlyCore(Protocol):
    def status(self) -> dict[str, Any]: ...
    def alerts(self, limit: int = 200) -> dict[str, Any]: ...


class CoreReadOnlyGateway:
    """Allow-listed read-only facade over the ventilation-core transport.

    The Home Assistant boundary never receives the generic ``request`` method.
    Only the two core commands required for monitoring are exposed here.
    """

    def __init__(self, transport: CoreClient) -> None:
        self._transport = transport

    def status(self) -> dict[str, Any]:
        response = self._transport.request({"command": "status"})
        if response.get("ok") is not True or not isinstance(response.get("state"), dict):
            raise CoreClientError(str(response.get("error") or "ventilation-core rejected status request"))
        return response

    def alerts(self, limit: int = 200) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer in range 1..1000")
        response = self._transport.request({"command": "alerts", "limit": limit})
        if (
            response.get("ok") is not True
            or not isinstance(response.get("active"), list)
            or not isinstance(response.get("history"), list)
        ):
            raise CoreClientError(str(response.get("error") or "ventilation-core rejected alerts request"))
        return response
