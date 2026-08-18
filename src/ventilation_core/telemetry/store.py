from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

from .rollup import RollupSample, floor_utc, summarize_metrics


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_aware_iso(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("telemetry timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


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
    """Local CM5 telemetry history, rollups and durable pending queue.

    Raw samples are also the delivery queue until acknowledged by the logical
    AI Bridge / Data Gateway. Retention is therefore allowed to delete only
    synchronized raw rows, and only after both local rollup resolutions have
    processed the time range being removed.
    """

    ROLLUPS = {
        "1m": ("telemetry_rollup_1m", 60),
        "15m": ("telemetry_rollup_15m", 15 * 60),
    }

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

                CREATE TABLE IF NOT EXISTS telemetry_rollup_1m (
                    bucket_start TEXT PRIMARY KEY,
                    bucket_end TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    rollup_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telemetry_rollup_15m (
                    bucket_start TEXT PRIMARY KEY,
                    bucket_end TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    rollup_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telemetry_rollup_state (
                    resolution TEXT PRIMARY KEY,
                    processed_until TEXT NOT NULL
                );
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
        _parse_aware_iso(effective_captured_at)
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

    def build_rollups(
        self,
        *,
        now: datetime | None = None,
        max_buckets_per_resolution: int = 240,
    ) -> dict[str, int]:
        if max_buckets_per_resolution < 1:
            raise ValueError("max_buckets_per_resolution must be at least 1")
        effective_now = now or datetime.now(timezone.utc)
        if effective_now.tzinfo is None or effective_now.utcoffset() is None:
            raise ValueError("rollup time must be timezone-aware")
        effective_now = effective_now.astimezone(timezone.utc)

        results: dict[str, int] = {}
        with self._connect() as connection:
            for resolution, (table, bucket_seconds) in self.ROLLUPS.items():
                results[resolution] = self._build_resolution(
                    connection,
                    resolution=resolution,
                    table=table,
                    bucket_seconds=bucket_seconds,
                    now=effective_now,
                    max_buckets=max_buckets_per_resolution,
                )
        return results

    def _build_resolution(
        self,
        connection: sqlite3.Connection,
        *,
        resolution: str,
        table: str,
        bucket_seconds: int,
        now: datetime,
        max_buckets: int,
    ) -> int:
        state = connection.execute(
            "SELECT processed_until FROM telemetry_rollup_state WHERE resolution = ?",
            (resolution,),
        ).fetchone()

        if state is None:
            earliest = connection.execute(
                "SELECT MIN(captured_at) AS captured_at FROM telemetry_samples"
            ).fetchone()
            if earliest is None or earliest["captured_at"] is None:
                return 0
            cursor = floor_utc(_parse_aware_iso(str(earliest["captured_at"])), bucket_seconds)
        else:
            cursor = _parse_aware_iso(str(state["processed_until"]))

        closed_until = floor_utc(now, bucket_seconds)
        created = 0
        processed = 0

        while cursor < closed_until and processed < max_buckets:
            bucket_end = cursor + timedelta(seconds=bucket_seconds)
            start_iso = cursor.isoformat()
            end_iso = bucket_end.isoformat()
            rows = connection.execute(
                """
                SELECT captured_at, metrics_json
                FROM telemetry_samples
                WHERE captured_at >= ? AND captured_at < ?
                ORDER BY sequence
                """,
                (start_iso, end_iso),
            ).fetchall()

            if rows:
                summary = summarize_metrics(
                    RollupSample(
                        captured_at=str(row["captured_at"]),
                        metrics=json.loads(str(row["metrics_json"])),
                    )
                    for row in rows
                )
                summary.update(
                    {
                        "resolution": resolution,
                        "bucket_start": start_iso,
                        "bucket_end": end_iso,
                    }
                )
                rollup_json = json.dumps(
                    summary,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                inserted = connection.execute(
                    f"""
                    INSERT OR IGNORE INTO {table}(
                        bucket_start, bucket_end, sample_count, rollup_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        start_iso,
                        end_iso,
                        len(rows),
                        rollup_json,
                        utc_now_iso(),
                    ),
                )
                if inserted.rowcount:
                    created += 1

            cursor = bucket_end
            processed += 1

        if processed:
            connection.execute(
                """
                INSERT INTO telemetry_rollup_state(resolution, processed_until)
                VALUES (?, ?)
                ON CONFLICT(resolution)
                DO UPDATE SET processed_until = excluded.processed_until
                """,
                (resolution, cursor.isoformat()),
            )

        return created

    def prune_history(
        self,
        *,
        raw_retention_days: int,
        minute_retention_days: int,
        quarter_retention_days: int,
        now: datetime | None = None,
    ) -> dict[str, int]:
        for name, value in (
            ("raw_retention_days", raw_retention_days),
            ("minute_retention_days", minute_retention_days),
            ("quarter_retention_days", quarter_retention_days),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")

        effective_now = now or datetime.now(timezone.utc)
        if effective_now.tzinfo is None or effective_now.utcoffset() is None:
            raise ValueError("retention time must be timezone-aware")
        effective_now = effective_now.astimezone(timezone.utc)

        raw_cutoff = effective_now - timedelta(days=raw_retention_days)
        minute_cutoff = effective_now - timedelta(days=minute_retention_days)
        quarter_cutoff = effective_now - timedelta(days=quarter_retention_days)

        deleted_raw = 0
        with self._connect() as connection:
            state_rows = connection.execute(
                """
                SELECT resolution, processed_until
                FROM telemetry_rollup_state
                WHERE resolution IN ('1m', '15m')
                """
            ).fetchall()
            processed_until = {
                str(row["resolution"]): _parse_aware_iso(str(row["processed_until"]))
                for row in state_rows
            }

            if "1m" in processed_until and "15m" in processed_until:
                safe_until = min(processed_until["1m"], processed_until["15m"])
                delete_before = min(raw_cutoff, safe_until)
                cursor = connection.execute(
                    """
                    DELETE FROM telemetry_samples
                    WHERE synced_at IS NOT NULL AND captured_at < ?
                    """,
                    (delete_before.isoformat(),),
                )
                deleted_raw = int(cursor.rowcount)

            minute_cursor = connection.execute(
                "DELETE FROM telemetry_rollup_1m WHERE bucket_start < ?",
                (minute_cutoff.isoformat(),),
            )
            quarter_cursor = connection.execute(
                "DELETE FROM telemetry_rollup_15m WHERE bucket_start < ?",
                (quarter_cutoff.isoformat(),),
            )

        return {
            "raw": deleted_raw,
            "1m": int(minute_cursor.rowcount),
            "15m": int(quarter_cursor.rowcount),
        }

    def prune_synced(self, retention_days: int) -> int:
        """Legacy direct raw prune retained for compatibility with older tooling/tests."""
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

    def rollup_count(self, resolution: str) -> int:
        try:
            table, _ = self.ROLLUPS[resolution]
        except KeyError as exc:
            raise ValueError("resolution must be '1m' or '15m'") from exc
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        assert row is not None
        return int(row["count"])

    def database_size_bytes(self) -> int:
        with self._connect() as connection:
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        return page_count * page_size
