from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from .history import (
    TelemetryHistoryReader,
    TelemetryHistoryStatus,
    TelemetryHistoryUnavailable,
)


@dataclass(frozen=True)
class LongRangeTelemetryHistoryStatus(TelemetryHistoryStatus):
    rollup_1h_samples: int = 0
    rollup_1d_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["rollup_1h_samples"] = self.rollup_1h_samples
        payload["rollup_1d_samples"] = self.rollup_1d_samples
        return payload


class LongRangeTelemetryHistoryReader(TelemetryHistoryReader):
    """Read-only telemetry history with hourly and daily rollup support."""

    MAX_QUERY_SAMPLES = 2500
    ROLLUP_TABLES = {
        **TelemetryHistoryReader.ROLLUP_TABLES,
        "1h": "telemetry_rollup_1h",
        "1d": "telemetry_rollup_1d",
    }

    def status(self) -> LongRangeTelemetryHistoryStatus:
        base = super().status()
        hourly = 0
        daily = 0
        if base.available:
            try:
                with self._connect() as connection:
                    hourly = self._count_table(connection, "telemetry_rollup_1h")
                    daily = self._count_table(connection, "telemetry_rollup_1d")
            except sqlite3.Error as exc:
                raise TelemetryHistoryUnavailable(str(exc)) from exc
        return LongRangeTelemetryHistoryStatus(
            available=base.available,
            total_samples=base.total_samples,
            pending_samples=base.pending_samples,
            synced_samples=base.synced_samples,
            oldest_captured_at=base.oldest_captured_at,
            newest_captured_at=base.newest_captured_at,
            oldest_pending_at=base.oldest_pending_at,
            last_synced_at=base.last_synced_at,
            rollup_1m_samples=base.rollup_1m_samples,
            rollup_15m_samples=base.rollup_15m_samples,
            database_bytes=base.database_bytes,
            rollup_1h_samples=hourly,
            rollup_1d_samples=daily,
        )

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
