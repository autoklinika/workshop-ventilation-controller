from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

from ventilation_core.calendar.model import CalendarConfig


class SqliteCalendarStore:
    """Atomic, versioned persistence for the complete Calendar Engine config."""

    def __init__(self, path: Path, *, initial_config: CalendarConfig | None = None) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self._path, timeout=5.0, check_same_thread=False)
        try:
            with self._lock:
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA synchronous=FULL")
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS calendar_configuration (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        revision INTEGER NOT NULL CHECK (revision >= 1),
                        schema_version INTEGER NOT NULL,
                        config_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                row = self._connection.execute(
                    "SELECT singleton FROM calendar_configuration WHERE singleton = 1"
                ).fetchone()
                if row is None and initial_config is not None:
                    self._insert_initial(initial_config)
                self._connection.commit()
        except BaseException:
            self._connection.close()
            raise

    def _insert_initial(self, config: CalendarConfig) -> None:
        self._connection.execute(
            "INSERT INTO calendar_configuration(singleton, revision, schema_version, config_json) VALUES(1, 1, ?, ?)",
            (config.schema_version, json.dumps(config.to_dict(), separators=(",", ":"), sort_keys=True)),
        )

    def load(self) -> tuple[CalendarConfig, int]:
        with self._lock:
            row = self._connection.execute(
                "SELECT revision, config_json FROM calendar_configuration WHERE singleton = 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("Calendar Engine configuration is not initialized")
            payload = json.loads(str(row[1]))
            return CalendarConfig.from_dict(payload), int(row[0])

    def replace(self, config: CalendarConfig) -> int:
        encoded = json.dumps(config.to_dict(), separators=(",", ":"), sort_keys=True)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT revision FROM calendar_configuration WHERE singleton = 1"
                ).fetchone()
                revision = 1 if row is None else int(row[0]) + 1
                self._connection.execute(
                    """
                    INSERT INTO calendar_configuration(singleton, revision, schema_version, config_json, updated_at)
                    VALUES(1, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(singleton) DO UPDATE SET
                        revision=excluded.revision,
                        schema_version=excluded.schema_version,
                        config_json=excluded.config_json,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (revision, config.schema_version, encoded),
                )
                self._connection.commit()
                return revision
            except BaseException:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()
