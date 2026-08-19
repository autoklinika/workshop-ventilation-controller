from __future__ import annotations

from typing import Any

from .history import TelemetryHistoryReader, TelemetryHistoryUnavailable


class LongRangeTelemetryHistoryReader(TelemetryHistoryReader):
    """Read-only telemetry history with hourly and daily rollup support."""

    MAX_QUERY_SAMPLES = 2500
    ROLLUP_TABLES = {
        **TelemetryHistoryReader.ROLLUP_TABLES,
        "1h": "telemetry_rollup_1h",
        "1d": "telemetry_rollup_1d",
    }

    def query(
        self,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        limit: int = 720,
        resolution: str = "raw",
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("history limit must be an integer")
        if not 1 <= limit <= self.MAX_QUERY_SAMPLES:
            raise ValueError(f"history limit must be within 1..{self.MAX_QUERY_SAMPLES}")
        supported = ("raw", *self.ROLLUP_TABLES.keys())
        if resolution not in supported:
            raise ValueError(
                "history resolution must be one of: " + ", ".join(supported)
            )
        if not self.path.is_file():
            raise TelemetryHistoryUnavailable("local telemetry database is not available")

        self._validate_range_value(start_at, "start_at")
        self._validate_range_value(end_at, "end_at")

        if resolution == "raw":
            return self._query_raw(start_at=start_at, end_at=end_at, limit=limit)
        return self._query_rollup(
            resolution=resolution,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )
