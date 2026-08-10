from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class AIBridgeTelemetryClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def send_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        target = f"{self.base_url}/api/v1/ventilation/telemetry/batches"
        req = request.Request(
            target,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                response_body = response.read()
                status = response.status
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI Bridge HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"AI Bridge unavailable: {exc.reason}") from exc

        if status != 200:
            raise RuntimeError(f"AI Bridge returned unexpected HTTP status {status}")
        decoded = json.loads(response_body.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise RuntimeError("AI Bridge returned an invalid ACK payload")
        return decoded
