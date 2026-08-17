from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any
import json


class TelemetryHistoryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class TelemetryHistoryStatus:
    available: bool
    total_samples: int
    pending_samples: int
    synced_samples: int
    oldest_captured_at: str | None
    newest_captured_at: str | None
    oldest_pending_at: str | None
    last_synced_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "total_samples": self.total_samples,
            "pending_samples": self.pending_samples,
            "synced_samples": self.synced_samples,
            "oldest_captured_at": self.oldest_captured_at,
            "newest_captured_at": self.newest_captured_at,
            "oldest_pending_at": self.oldest_pending_at,
            "last_synced_at": self.last_synced_at,
        }


class TelemetryHistoryReader:
    """Read-only view of the local telemetry SQLite database for Web/API clients."""

    MAX_QUERY_SAMPLES = 2000

    def __init__(self, path: Path) -> None:
        self.path = path

    def status(self) -> TelemetryHistoryStatus:
        if not self.path.is_file():
            return TelemetryHistoryStatus(
                available=False,
                total_samples=0,
                pending_samples=0,
                synced_samples=0,
                oldest_captured_at=None,
                newest_captured_at=None,
                oldest_pending_at=None,
                last_synced_at=None,
            )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total_samples,
                        SUM(CASE WHEN synced_at IS NULL THEN 1 ELSE 0 END) AS pending_samples,
                        SUM(CASE WHEN synced_at IS NOT NULL THEN 1 ELSE 0 END) AS synced_samples,
                        MIN(captured_at) AS oldest_captured_at,
                        MAX(captured_at) AS newest_captured_at,
                        MIN(CASE WHEN synced_at IS NULL THEN captured_at END) AS oldest_pending_at,
                        MAX(synced_at) AS last_synced_at
                    FROM telemetry_samples
                    """
                ).fetchone()
        except sqlite3.Error as exc:
            raise TelemetryHistoryUnavailable(str(exc)) from exc

        assert row is not None
        return TelemetryHistoryStatus(
            available=True,
            total_samples=int(row["total_samples"] or 0),
            pending_samples=int(row["pending_samples"] or 0),
            synced_samples=int(row["synced_samples"] or 0),
            oldest_captured_at=row["oldest_captured_at"],
            newest_captured_at=row["newest_captured_at"],
            oldest_pending_at=row["oldest_pending_at"],
            last_synced_at=row["last_synced_at"],
        )

    def query(
        self,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        limit: int = 720,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("history limit must be an integer")
        if not 1 <= limit <= self.MAX_QUERY_SAMPLES:
            raise ValueError(f"history limit must be within 1..{self.MAX_QUERY_SAMPLES}")
        if not self.path.is_file():
            raise TelemetryHistoryUnavailable("local telemetry database is not available")

        clauses: list[str] = []
        params: list[Any] = []
        if start_at is not None:
            if not isinstance(start_at, str) or not start_at:
                raise ValueError("start_at must be a non-empty ISO-8601 string")
            clauses.append("captured_at >= ?")
            params.append(start_at)
        if end_at is not None:
            if not isinstance(end_at, str) or not end_at:
                raise ValueError("end_at must be a non-empty ISO-8601 string")
            clauses.append("captured_at <= ?")
            params.append(end_at)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT sequence, sample_id, captured_at, metrics_json, synced_at
                    FROM telemetry_samples
                    {where}
                    ORDER BY sequence DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise TelemetryHistoryUnavailable(str(exc)) from exc

        result = [
            {
                "sequence": int(row["sequence"]),
                "sample_id": str(row["sample_id"]),
                "captured_at": str(row["captured_at"]),
                "synced": row["synced_at"] is not None,
                "metrics": json.loads(str(row["metrics_json"])),
            }
            for row in reversed(rows)
        ]
        return result

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
