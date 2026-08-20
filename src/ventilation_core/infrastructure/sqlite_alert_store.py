from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from threading import RLock

from ventilation_core.domain.alerts import AlertRecord, AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity


LOGGER = logging.getLogger(__name__)
VOLATILE_FALLBACK_ENV = "WVC_ALERT_STORE_ALLOW_VOLATILE_FALLBACK"
REQUIRED_MOUNT_ENV = "WVC_ALERT_STORE_REQUIRED_MOUNT"


def _volatile_fallback_enabled() -> bool:
    return os.getenv(VOLATILE_FALLBACK_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _required_mount() -> Path | None:
    raw = os.getenv(REQUIRED_MOUNT_ENV, "").strip()
    return Path(raw) if raw else None


def _validate_required_mount(path: Path) -> None:
    required = _required_mount()
    if required is None:
        return

    target = path.resolve(strict=False)
    mount_root = required.resolve(strict=False)
    try:
        target.relative_to(mount_root)
    except ValueError:
        return

    if not os.path.ismount(mount_root):
        raise OSError(
            f"required persistent-data mount is not mounted: {mount_root}"
        )


class SqliteAlertStore:
    """Persistent alert journal owned by ventilation-core.

    Writes occur only on lifecycle transitions or when alert details materially
    change. Production stores the journal on the NVMe data tier. If that tier is
    unavailable, ``WVC_ALERT_STORE_ALLOW_VOLATILE_FALLBACK=1`` allows the core
    to continue with an in-memory alert journal instead of falling back to eMMC
    or refusing to start. ``WVC_ALERT_STORE_REQUIRED_MOUNT`` prevents the
    underlying mountpoint directory on eMMC from being mistaken for a mounted
    data tier. The fallback is intentionally explicit and logged at CRITICAL
    severity.

    Alert history is intentionally not pruned automatically. The project keeps
    the full local journal while the ventilation system is being characterized;
    retention will be reviewed only after at least one year of operational data
    has been collected.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = RLock()
        self._persistent = True
        self._connection: sqlite3.Connection | None = None

        try:
            _validate_required_mount(self._path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = self._open_connection(self._path)
            self._initialize_schema()
        except (OSError, sqlite3.Error) as exc:
            if self._connection is not None:
                try:
                    self._connection.close()
                except sqlite3.Error:
                    pass
                self._connection = None
            if not _volatile_fallback_enabled():
                raise
            self._persistent = False
            LOGGER.critical(
                "Persistent alert journal unavailable at %s; using volatile RAM fallback: %s",
                self._path,
                exc,
            )
            self._connection = self._open_connection(":memory:")
            self._initialize_schema()

    @staticmethod
    def _open_connection(path: Path | str) -> sqlite3.Connection:
        connection = sqlite3.connect(
            path,
            timeout=5.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        assert self._connection is not None
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
                """
            )
            self._connection.commit()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def persistent(self) -> bool:
        return self._persistent

    @property
    def using_volatile_fallback(self) -> bool:
        return not self._persistent

    @property
    def _db(self) -> sqlite3.Connection:
        assert self._connection is not None
        return self._connection

    def list_active(self) -> tuple[AlertRecord, ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM alerts WHERE cleared_at IS NULL ORDER BY alert_id ASC"
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    def list_history(self, limit: int) -> tuple[AlertRecord, ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM alerts ORDER BY alert_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    def create(self, signal: AlertSignal, active_since: str) -> AlertRecord:
        with self._lock:
            cursor = self._db.execute(
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
            self._db.commit()
            return self._get(int(cursor.lastrowid))

    def update_active(self, record: AlertRecord, signal: AlertSignal) -> AlertRecord:
        with self._lock:
            self._db.execute(
                """
                UPDATE alerts
                   SET code = ?, source = ?, severity = ?, message = ?, detail = ?,
                       occurrences = ?
                 WHERE alert_id = ? AND cleared_at IS NULL
                """,
                (
                    signal.code.value,
                    signal.source,
                    signal.severity.value,
                    signal.message,
                    signal.detail,
                    max(record.occurrences, signal.occurrences),
                    record.alert_id,
                ),
            )
            self._db.commit()
            return self._get(record.alert_id)

    def acknowledge(self, alert_id: int, acknowledged_at: str) -> AlertRecord:
        with self._lock:
            cursor = self._db.execute(
                """
                UPDATE alerts
                   SET acknowledged_at = COALESCE(acknowledged_at, ?)
                 WHERE alert_id = ? AND cleared_at IS NULL
                """,
                (acknowledged_at, alert_id),
            )
            self._db.commit()
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
            cursor = self._db.execute(
                """
                UPDATE alerts
                   SET cleared_at = COALESCE(cleared_at, ?),
                       occurrences = MAX(occurrences, ?)
                 WHERE alert_id = ?
                """,
                (cleared_at, occurrences, alert_id),
            )
            self._db.commit()
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown alert id: {alert_id}")
            return self._get(alert_id)

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _get(self, alert_id: int) -> AlertRecord:
        row = self._db.execute(
            "SELECT * FROM alerts WHERE alert_id = ?",
            (alert_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown alert id: {alert_id}")
        return self._row_to_record(row)

    def _find(self, alert_id: int) -> AlertRecord | None:
        row = self._db.execute(
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
