from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from urllib import error, parse, request


_ALLOWED_STATUSES = {
    "no_anomaly_detected",
    "attention",
    "anomaly",
    "insufficient_data",
}


def _require_aware_datetime(payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if not isinstance(value, str):
        raise RuntimeError(f"AI advisory field {field!r} must be an ISO timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"AI advisory field {field!r} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"AI advisory field {field!r} must include timezone information")


def validate_advisory_delivery(
    payload: dict[str, Any],
    *,
    expected_source_id: str,
) -> dict[str, Any]:
    """Validate only the transport/safety contract, never the semantic AI advice."""

    if payload.get("delivery_schema_version") != 1:
        raise RuntimeError("AI Bridge returned unsupported advisory delivery schema")
    if payload.get("source_id") != expected_source_id:
        raise RuntimeError("AI Bridge returned advisory data for an unexpected source_id")
    if not isinstance(payload.get("analysis_id"), str) or not payload["analysis_id"]:
        raise RuntimeError("AI Bridge returned an invalid analysis_id")
    if payload.get("advisory_only") is not True:
        raise RuntimeError("AI advisory payload is missing advisory_only=true")
    if payload.get("experimental") is not True:
        raise RuntimeError("AI advisory payload is missing experimental=true")
    if payload.get("control_actions_supported") is not False:
        raise RuntimeError("AI advisory payload must declare control_actions_supported=false")

    for field in ("window_start", "window_end", "created_at"):
        _require_aware_datetime(payload, field)

    if not isinstance(payload.get("sample_count"), int) or payload["sample_count"] < 0:
        raise RuntimeError("AI advisory sample_count is invalid")
    if not isinstance(payload.get("model"), str) or not payload["model"]:
        raise RuntimeError("AI advisory model is invalid")
    if not isinstance(payload.get("prompt_version"), str) or not payload["prompt_version"]:
        raise RuntimeError("AI advisory prompt_version is invalid")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("AI advisory result must be an object")
    if result.get("schema_version") != 2:
        raise RuntimeError("AI advisory result schema is unsupported")
    if result.get("status") not in _ALLOWED_STATUSES:
        raise RuntimeError("AI advisory result status is invalid")
    for field in ("analysis_pl", "operator_recommendation_pl", "data_quality_pl"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise RuntimeError(f"AI advisory result field {field!r} is invalid")

    return payload


class AIBridgeAdvisoryClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_latest(self, source_id: str) -> dict[str, Any] | None:
        query = parse.urlencode({"source_id": source_id})
        target = f"{self.base_url}/api/v1/ventilation/analysis/latest?{query}"
        req = request.Request(
            target,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                response_body = response.read()
                status = response.status
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI Bridge advisory HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"AI Bridge advisory unavailable: {exc.reason}") from exc

        if status != 200:
            raise RuntimeError(f"AI Bridge advisory returned unexpected HTTP status {status}")

        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("AI Bridge advisory returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("AI Bridge advisory returned an invalid payload")
        return validate_advisory_delivery(decoded, expected_source_id=source_id)
