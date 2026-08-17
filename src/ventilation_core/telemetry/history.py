from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


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
    rollup_1m_samples: int = 0
    rollup_15m_samples: int = 0
    database_bytes: int = 0

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
            "rollup_1m_samples": self.rollup_1m_samples,
            "rollup_15m_samples": self.rollup_15m_samples,
            "database_bytes": self.database_bytes,
        }


class TelemetryHistoryReader:
    """Read-only view of the local telemetry SQLite database for Web/API clients."""

    MAX_QUERY_SAMPLES = 2000
    ROLLUP_TABLES = {"1m": "telemetry_rollup_1m", "15m": "telemetry_rollup_15m"}

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
                rollup_1m = self._count_table(connection, "telemetry_rollup_1m")
                rollup_15m = self._count_table(connection, "telemetry_rollup_15m")
                page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
                page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
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
            rollup_1m_samples=rollup_1m,
            rollup_15m_samples=rollup_15m,
            database_bytes=page_count * page_size,
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
        if resolution not in {"raw", "1m", "15m"}:
            raise ValueError("history resolution must be one of: raw, 1m, 15m")
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

    def _query_raw(
        self,
        *,
        start_at: str | None,
        end_at: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if start_at is not None:
            clauses.append("captured_at >= ?")
            params.append(start_at)
        if end_at is not None:
            clauses.append("captured_at <= ?")
            params.append(end_at)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""

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

        return [
            {
                "resolution": "raw",
                "sequence": int(row["sequence"]),
                "sample_id": str(row["sample_id"]),
                "captured_at": str(row["captured_at"]),
                "synced": row["synced_at"] is not None,
                "metrics": json.loads(str(row["metrics_json"])),
            }
            for row in reversed(rows)
        ]

    def _query_rollup(
        self,
        *,
        resolution: str,
        start_at: str | None,
        end_at: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        table = self.ROLLUP_TABLES[resolution]
        clauses: list[str] = []
        params: list[Any] = []
        if start_at is not None:
            clauses.append("bucket_end >= ?")
            params.append(start_at)
        if end_at is not None:
            clauses.append("bucket_start <= ?")
            params.append(end_at)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""

        try:
            with self._connect() as connection:
                if not self._table_exists(connection, table):
                    return []
                rows = connection.execute(
                    f"""
                    SELECT bucket_start, bucket_end, sample_count, rollup_json
                    FROM {table}
                    {where}
                    ORDER BY bucket_start DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise TelemetryHistoryUnavailable(str(exc)) from exc

        return [
            {
                "resolution": resolution,
                "bucket_start": str(row["bucket_start"]),
                "bucket_end": str(row["bucket_end"]),
                "sample_count": int(row["sample_count"]),
                "rollup": json.loads(str(row["rollup_json"])),
            }
            for row in reversed(rows)
        ]

    @staticmethod
    def _validate_range_value(value: str | None, name: str) -> None:
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"{name} must be a non-empty ISO-8601 string")

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _count_table(self, connection: sqlite3.Connection, table: str) -> int:
        if not self._table_exists(connection, table):
            return 0
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        assert row is not None
        return int(row["count"] or 0)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            f"file:{self.path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()
