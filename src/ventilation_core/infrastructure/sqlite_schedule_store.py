from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from typing import Sequence

from ventilation_core.domain.schedule import ScheduleExpectation, ScheduleWindow, validate_windows


class SqliteScheduleStore:
    """Persistent, low-write schedule configuration stored beside other core state."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        connection = sqlite3.connect(
            self._path,
            timeout=5.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        self._connection = connection
        try:
            with self._lock:
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA synchronous=FULL")
                self._connection.execute("PRAGMA foreign_keys=ON")
                self._connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schedule_windows (
                        window_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        zone TEXT NOT NULL,
                        weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
                        start_minute INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1439),
                        end_minute INTEGER NOT NULL CHECK (end_minute BETWEEN 0 AND 1439),
                        expectation TEXT NOT NULL,
                        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                        label TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS schedule_windows_zone_order
                        ON schedule_windows(zone, weekday, start_minute, window_id);
                    """
                )
                self._connection.commit()
        except BaseException:
            self._connection.close()
            raise

    @property
    def path(self) -> Path:
        return self._path

    def list_windows(self, zone: str | None = None) -> tuple[ScheduleWindow, ...]:
        with self._lock:
            if zone is None:
                rows = self._connection.execute(
                    """
                    SELECT * FROM schedule_windows
                    ORDER BY zone ASC, weekday ASC, start_minute ASC, window_id ASC
                    """
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM schedule_windows
                    WHERE zone = ?
                    ORDER BY weekday ASC, start_minute ASC, window_id ASC
                    """,
                    (zone,),
                ).fetchall()
            windows = tuple(self._row_to_window(row) for row in rows)
            validate_windows(windows)
            return windows

    def replace_zone(
        self,
        zone: str,
        windows: Sequence[ScheduleWindow],
    ) -> tuple[ScheduleWindow, ...]:
        window_tuple = tuple(windows)
        if any(window.zone != zone for window in window_tuple):
            raise ValueError("Every replacement window must belong to the selected zone")
        validate_windows(window_tuple)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute("DELETE FROM schedule_windows WHERE zone = ?", (zone,))
                for window in window_tuple:
                    self._connection.execute(
                        """
                        INSERT INTO schedule_windows (
                            zone, weekday, start_minute, end_minute,
                            expectation, enabled, label
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            window.zone,
                            window.weekday,
                            window.start_minute,
                            window.end_minute,
                            window.expectation.value,
                            1 if window.enabled else 0,
                            window.label,
                        ),
                    )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
            return self.list_windows(zone)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _row_to_window(row: sqlite3.Row) -> ScheduleWindow:
        return ScheduleWindow(
            window_id=int(row["window_id"]),
            zone=str(row["zone"]),
            weekday=int(row["weekday"]),
            start_minute=int(row["start_minute"]),
            end_minute=int(row["end_minute"]),
            expectation=ScheduleExpectation(str(row["expectation"])),
            enabled=bool(row["enabled"]),
            label=str(row["label"]),
        )
