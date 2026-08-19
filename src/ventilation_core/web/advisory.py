from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ventilation_core.advisory.cache import AdvisoryCache
from ventilation_core.advisory.client import validate_advisory_delivery


DEFAULT_SOURCE_ID = "workshop-ventilation-cm5-01"
DEFAULT_STALE_AFTER_SECONDS = 30 * 60


class AdvisoryError(RuntimeError):
    pass


class FileAdvisoryProvider:
    """Read-only Web UI adapter for the local CM5 AI advisory cache."""

    def __init__(
        self,
        path: Path,
        *,
        expected_source_id: str = DEFAULT_SOURCE_ID,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")

        self._cache = AdvisoryCache(path)
        self._expected_source_id = expected_source_id
        self._stale_after_seconds = stale_after_seconds

    def get_snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        try:
            cached = self._cache.load()
        except RuntimeError as exc:
            raise AdvisoryError(str(exc)) from exc

        if cached is None:
            return {
                "available": False,
                "configured": True,
                "source": "local-cache",
                "stale": True,
                "fresh": False,
                "stale_after_seconds": self._stale_after_seconds,
                "error": "AI advisory cache is not available yet",
            }

        report = cached.get("report")
        if not isinstance(report, dict):
            raise AdvisoryError("AI advisory cache report is invalid")

        try:
            validate_advisory_delivery(
                report,
                expected_source_id=self._expected_source_id,
            )
        except RuntimeError as exc:
            raise AdvisoryError(str(exc)) from exc

        window_end_raw = report["window_end"]
        window_end = datetime.fromisoformat(
            window_end_raw.replace("Z", "+00:00")
        )

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise AdvisoryError("current time must include timezone information")

        age_seconds = max(
            0,
            int((current.astimezone(timezone.utc) - window_end.astimezone(timezone.utc)).total_seconds()),
        )
        stale = age_seconds > self._stale_after_seconds

        return {
            "available": True,
            "configured": True,
            "source": "local-cache",
            "fresh": not stale,
            "stale": stale,
            "stale_after_seconds": self._stale_after_seconds,
            "age_seconds": age_seconds,
            "fetched_at": cached.get("fetched_at"),
            "report": report,
        }
