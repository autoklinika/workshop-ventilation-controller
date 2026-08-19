from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from pathlib import Path
from threading import RLock

from ventilation_core.domain.alerts import AlertRecord, AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity


class SqliteAlertStore:
    """Persistent alert journal owned by ventilation-core.

    Writes occur only on lifecycle transitions or when alert details materially
    change, so normal 1 Hz health supervision does not generate continuous eMMC
    writes. Occurrence-only growth is batched by AlertRegistry; the final exact
    count is written together with the CLEARED transition.

    Cleared incidents are retained for 30 days. Active incidents are never
    removed by retention, regardless of how long they have been active. Physical
    pruning runs at startup, on lifecycle transitions and at most once per UTC
    day when history is read; the read path also filters the 30-day window so an
    expired cleared record is never exposed while waiting for the next prune.
    """

    HISTORY_RETENTION_DAYS = 30

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self._path,
            timeout=5.0,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._last_prune_date = None
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_key TEXT NOT NULL,
                    code TEXT NOT NULL,
                    source TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    active_since TEXT NOT NULL,
                    acknowledged_at TEXT,
                    cleared_at TEXT,
                    occurrences INTEGER NOT NULL DEFAULT 1 CHECK (occurrences >= 1)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_active_key
                    ON alerts(alert_key)
                    WHERE cleared_at IS NULL;
                CREATE INDEX IF NOT EXISTS alerts_history_order
                    ON alerts(alert_id DESC);
                CREATE INDEX IF NOT EXISTS alerts_cleared_at
                    ON alerts(cleared_at);
                """
            )
            now = datetime.now(timezone.utc)
            self._prune_history_unlocked(now)
            self._last_prune_date = now.date()
            self._connection.commit()

    @property
    def path(self) -> Path:
        return self._path

    def list_active(self) -> tuple[AlertRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM alerts WHERE cleared_at IS NULL ORDER BY alert_id ASC"
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    def list_history(self, limit: int) -> tuple[AlertRecord, ...]:
        now = datetime.now(timezone.utc)
        cutoff = self._history_cutoff(now)
        with self._lock:
            self._maybe_prune_history_unlocked(now)
            rows = self._connection.execute(
                """
                SELECT *
                FROM alerts
                WHERE cleared_at IS NULL OR cleared_at >= ?
                ORDER BY alert_id DESC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    def prune_history(self, *, now: datetime | None = None) -> int:
        """Delete cleared incidents older than retention; active alerts survive."""
        effective_now = now or datetime.now(timezone.utc)
        if effective_now.tzinfo is None or effective_now.utcoffset() is None:
            raise ValueError("alert retention time must be timezone-aware")
        effective_now = effective_now.astimezone(timezone.utc)
        with self._lock:
            deleted = self._prune_history_unlocked(effective_now)
            self._last_prune_date = effective_now.date()
            self._connection.commit()
            return deleted

    def create(self, signal: AlertSignal, active_since: str) -> AlertRecord:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO alerts (
                    alert_key, code, source, severity, message, detail,
                    active_since, acknowledged_at, cleared_at, occurrences
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (
                    signal.key,
                    signal.code.value,
                    signal.source,
                    signal.severity.value,
                    signal.message,
                    signal.detail,
                    active_since,
                    signal.occurrences,
                ),
            )
            now = datetime.now(timezone.utc)
            self._prune_history_unlocked(now)
            self._last_prune_date = now.date()
            self._connection.commit()
            return self._get(int(cursor.lastrowid))

    def update_active(self, record: AlertRecord, signal: AlertSignal) -> AlertRecord:
        with self._lock:
            self._connection.execute(
                """
                UPDATE alerts
                   SET code = ?, source = ?, severity = ?, message = ?, detail = ?,
                       occurrences = ?
                 WHERE alert_id = ? AND cleared_at IS NULL
                """,
                (
                    signal.code.value,
                    signal.source.value if isinstance(signal.source, AlarmCode) else signal.source,
                    signal.severity.value,
                    signal.message,
                    signal.detail,
                    max(record.occurrences, signal.occurrences),
                    record.alert_id,
                ),
            )
            self._connection.commit()
            return self._get(record.alert_id)

    def acknowledge(self, alert_id: int, acknowledged_at: str) -> AlertRecord:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE alerts
                   SET acknowledged_at = COALESCE(acknowledged_at, ?)
                 WHERE alert_id = ? AND cleared_at IS NULL
                """,
                (acknowledged_at, alert_id),
            )
            self._connection.commit()
            if cursor.rowcount != 1:
                existing = self._find(alert_id)
                if existing is None:
                    raise ValueError(f"Unknown alert id: {alert_id}")
                raise ValueError(f"Alert {alert_id} is not active")
            return self._get(alert_id)

    def clear(
        self,
        alert_id: int,
        cleared_at: str,
        final_occurrences: int | None = None,
    ) -> AlertRecord:
        with self._lock:
            existing = self._find(alert_id)
            if existing is None:
                raise ValueError(f"Unknown alert id: {alert_id}")
            occurrences = max(
                existing.occurrences,
                final_occurrences or existing.occurrences,
            )
            cursor = self._connection.execute(
                """
                UPDATE alerts
                   SET cleared_at = COALESCE(cleared_at, ?),
                       occurrences = MAX(occurrences, ?)
                 WHERE alert_id = ?
                """,
                (cleared_at, occurrences, alert_id),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise ValueError(f"Unknown alert id: {alert_id}")
            record = self._get(alert_id)
            now = datetime.now(timezone.utc)
            self._prune_history_unlocked(now)
            self._last_prune_date = now.date()
            self._connection.commit()
            return record

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @classmethod
    def _history_cutoff(cls, now: datetime) -> str:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("alert retention time must be timezone-aware")
        return (
            now.astimezone(timezone.utc) - timedelta(days=cls.HISTORY_RETENTION_DAYS)
        ).isoformat()

    def _maybe_prune_history_unlocked(self, now: datetime) -> None:
        today = now.astimezone(timezone.utc).date()
        if self._last_prune_date == today:
            return
        self._prune_history_unlocked(now)
        self._last_prune_date = today
        self._connection.commit()

    def _prune_history_unlocked(self, now: datetime) -> int:
        cutoff = self._history_cutoff(now)
        cursor = self._connection.execute(
            """
            DELETE FROM alerts
            WHERE cleared_at IS NOT NULL AND cleared_at < ?
            """,
            (cutoff,),
        )
        return int(cursor.rowcount)

    def _get(self, alert_id: int) -> AlertRecord:
        row = self._connection.execute(
            "SELECT * FROM alerts WHERE alert_id = ?",
            (alert_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown alert id: {alert_id}")
        return self._row_to_record(row)

    def _find(self, alert_id: int) -> AlertRecord | None:
        row = self._connection.execute(
            "SELECT * FROM alerts WHERE alert_id = ?",
            (alert_id,),
        ).fetchone()
        return None if row is None else self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AlertRecord:
        return AlertRecord(
            alert_id=int(row["alert_id"]),
            key=str(row["alert_key"]),
            code=AlarmCode(str(row["code"])),
            source=str(row["source"]),
            severity=AlarmSeverity(str(row["severity"])),
            message=str(row["message"]),
            detail=str(row["detail"]),
            active_since=str(row["active_since"]),
            acknowledged_at=(
                None if row["acknowledged_at"] is None else str(row["acknowledged_at"])
            ),
            cleared_at=None if row["cleared_at"] is None else str(row["cleared_at"]),
            occurrences=int(row["occurrences"]),
        )
