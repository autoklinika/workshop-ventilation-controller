"""Atomic, revisioned storage of a planning-only autostart configuration."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from ventilation_core.domain.autostart import default_config, validate_config, year_days


class SqliteAutostartStore:
    def __init__(self, path: Path) -> None:
        self._lock = RLock()
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._path, check_same_thread=False, timeout=5)
        try:
            with self._lock:
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("PRAGMA synchronous=FULL")
                self._db.execute("""
                    CREATE TABLE IF NOT EXISTS autostart_plan (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        revision INTEGER NOT NULL CHECK(revision > 0),
                        payload TEXT NOT NULL
                    )
                """)
                self._db.execute(
                    "INSERT OR IGNORE INTO autostart_plan(singleton, revision, payload) VALUES (1, 1, ?)",
                    (json.dumps(default_config(), separators=(",", ":")),),
                )
                self._db.commit()
        except BaseException:
            self._db.close()
            raise

    def _read(self) -> tuple[dict[str, Any], int]:
        row = self._db.execute(
            "SELECT payload, revision FROM autostart_plan WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Autostart plan is missing")
        return validate_config(json.loads(row[0])), int(row[1])

    def get(self, year: int) -> dict[str, Any]:
        with self._lock:
            config, revision = self._read()
            return {
                "available": True,
                "revision": revision,
                "timezone": "Europe/Warsaw",
                "actuation_enabled": False,
                "config": config,
                "year": year,
                "days": year_days(config, year),
            }

    def replace(self, config: Any, expected_revision: int, year: int) -> dict[str, Any]:
        normalized = validate_config(config)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                _, revision = self._read()
                if expected_revision != revision:
                    raise ValueError("Autostart plan changed; reload before saving")
                self._db.execute(
                    "UPDATE autostart_plan SET revision = ?, payload = ? WHERE singleton = 1",
                    (revision + 1, json.dumps(normalized, separators=(",", ":"))),
                )
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
            return self.get(year)

    def close(self) -> None:
        with self._lock:
            self._db.close()
