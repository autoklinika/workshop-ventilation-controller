from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from zoneinfo import ZoneInfo

from .model import CalendarConfig, CalendarResolution, DEFAULT_TIMEZONE, unavailable_resolution
from .resolver import resolve_calendar


LOGGER = logging.getLogger(__name__)


class CalendarStore(Protocol):
    def load(self) -> tuple[CalendarConfig, int]: ...
    def replace(self, config: CalendarConfig) -> int: ...
    def close(self) -> None: ...


class CalendarEngine:
    def __init__(self, store: CalendarStore) -> None:
        self._store = store
        self._lock = RLock()

    def resolve(self, now_utc: datetime | None = None) -> CalendarResolution:
        now = now_utc or datetime.now(timezone.utc)
        with self._lock:
            try:
                config, _ = self._store.load()
                return resolve_calendar(config, now_utc=now)
            except Exception as exc:
                LOGGER.exception("Calendar Engine resolution failed")
                return unavailable_resolution(now_utc=now, timezone_name=DEFAULT_TIMEZONE, error=str(exc))

    def configuration(self, now_utc: datetime | None = None) -> dict[str, object]:
        with self._lock:
            config, revision = self._store.load()
            return {
                "available": True,
                "revision": revision,
                "config": config.to_dict(),
                "state": resolve_calendar(config, now_utc=now_utc).to_dict(),
            }

    def replace_configuration(self, payload: dict[str, object]) -> dict[str, object]:
        config = CalendarConfig.from_dict(payload)
        ZoneInfo(config.timezone)
        resolve_calendar(config, now_utc=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
        with self._lock:
            revision = self._store.replace(config)
            return {"available": True, "revision": revision, "config": config.to_dict()}

    def close(self) -> None:
        with self._lock:
            self._store.close()
