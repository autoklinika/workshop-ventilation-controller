from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TelemetrySampleRecord:
    sequence: int
    sample_id: str
    captured_at: str
    metrics: dict[str, Any]


@dataclass(frozen=True)
class TelemetryBatchRecord:
    batch_id: str
    created_at: str
    samples: tuple[TelemetrySampleRecord, ...]


class TelemetryStore:
    """Local CM5 telemetry history and durable pending queue."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_samples (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    sample_id TEXT NOT NULL UNIQUE,
                    captured_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    batch_id TEXT,
                    batch_created_at TEXT,
                    synced_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    last_error TEXT
                );

                CREATE INDEX IF NOT EXISTS ix_telemetry_pending
                    ON telemetry_samples(synced_at, batch_id, sequence);

                CREATE INDEX IF NOT EXISTS ix_telemetry_captured
                    ON telemetry_samples(captured_at);
                """
            )

    def append_snapshot(
        self,
        metrics: dict[str, Any],
        *,
        captured_at: str | None = None,
        sample_id: str | None = None,
    ) -> TelemetrySampleRecord:
        effective_captured_at = captured_at or utc_now_iso()
        effective_sample_id = sample_id or str(uuid4())
        metrics_json = json.dumps(
            metrics,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO telemetry_samples(sample_id, captured_at, metrics_json)
                VALUES (?, ?, ?)
                """,
                (effective_sample_id, effective_captured_at, metrics_json),
            )
            sequence = int(cursor.lastrowid)
        return TelemetrySampleRecord(
            sequence=sequence,
            sample_id=effective_sample_id,
            captured_at=effective_captured_at,
            metrics=metrics,
        )

    def reserve_batch(self, limit: int) -> TelemetryBatchRecord | None:
        if limit < 1:
            raise ValueError("Batch limit must be at least 1")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT batch_id, batch_created_at
                FROM telemetry_samples
                WHERE synced_at IS NULL AND batch_id IS NOT NULL
                ORDER BY sequence
                LIMIT 1
                """
            ).fetchone()

            if existing is None:
                rows = connection.execute(
                    """
                    SELECT sequence
                    FROM telemetry_samples
                    WHERE synced_at IS NULL AND batch_id IS NULL
                    ORDER BY sequence
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                if not rows:
                    return None

                batch_id = str(uuid4())
                created_at = utc_now_iso()
                sequences = [int(row["sequence"]) for row in rows]
                placeholders = ",".join("?" for _ in sequences)
                connection.execute(
                    f"""
                    UPDATE telemetry_samples
                    SET batch_id = ?, batch_created_at = ?
                    WHERE sequence IN ({placeholders})
                    """,
                    (batch_id, created_at, *sequences),
                )
            else:
                batch_id = str(existing["batch_id"])
                created_at = str(existing["batch_created_at"])

            sample_rows = connection.execute(
                """
                SELECT sequence, sample_id, captured_at, metrics_json
                FROM telemetry_samples
                WHERE synced_at IS NULL AND batch_id = ?
                ORDER BY sequence
                """,
                (batch_id,),
            ).fetchall()

        samples = tuple(
            TelemetrySampleRecord(
                sequence=int(row["sequence"]),
                sample_id=str(row["sample_id"]),
                captured_at=str(row["captured_at"]),
                metrics=json.loads(str(row["metrics_json"])),
            )
            for row in sample_rows
        )
        return TelemetryBatchRecord(
            batch_id=batch_id,
            created_at=created_at,
            samples=samples,
        )

    def record_attempt(self, batch_id: str, error: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE telemetry_samples
                SET attempts = attempts + 1,
                    last_attempt_at = ?,
                    last_error = ?
                WHERE synced_at IS NULL AND batch_id = ?
                """,
                (utc_now_iso(), error, batch_id),
            )

    def mark_batch_synced(self, batch_id: str) -> int:
        synced_at = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE telemetry_samples
                SET synced_at = ?, last_error = NULL
                WHERE synced_at IS NULL AND batch_id = ?
                """,
                (synced_at, batch_id),
            )
            return int(cursor.rowcount)

    def prune_synced(self, retention_days: int) -> int:
        if retention_days < 1:
            raise ValueError("Retention must be at least 1 day")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM telemetry_samples
                WHERE synced_at IS NOT NULL AND captured_at < ?
                """,
                (cutoff,),
            )
            return int(cursor.rowcount)

    def pending_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM telemetry_samples WHERE synced_at IS NULL"
            ).fetchone()
        assert row is not None
        return int(row["count"])

    def total_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM telemetry_samples").fetchone()
        assert row is not None
        return int(row["count"])
