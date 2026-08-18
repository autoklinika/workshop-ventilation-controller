from __future__ import annotations

import logging
from datetime import datetime
from threading import RLock
from typing import Protocol, Sequence
from zoneinfo import ZoneInfo

from ventilation_core.domain.schedule import (
    SCHEDULE_TIMEZONE,
    ScheduleState,
    ScheduleWindow,
    evaluate_schedule,
    unavailable_schedule_state,
    validate_windows,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_SCHEDULE_ZONES = ("zone-1", "zone-2")


class ScheduleStore(Protocol):
    def list_windows(self, zone: str | None = None) -> tuple[ScheduleWindow, ...]: ...
    def replace_zone(self, zone: str, windows: Sequence[ScheduleWindow]) -> tuple[ScheduleWindow, ...]: ...
    def close(self) -> None: ...


class ScheduleManager(Protocol):
    def current_state(self, now_utc: datetime | None = None) -> ScheduleState: ...
    def configuration(self, now_utc: datetime | None = None) -> dict[str, object]: ...
    def replace_zone(self, zone: str, windows: Sequence[ScheduleWindow]) -> dict[str, object]: ...
    def close(self) -> None: ...


def _normalize_zones(zones: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for zone in zones:
        if not isinstance(zone, str) or not zone or zone.strip() != zone or len(zone) > 64:
            raise ValueError("Schedule zones must be non-empty identifiers up to 64 characters")
        if zone in normalized:
            raise ValueError(f"Duplicate schedule zone: {zone}")
        normalized.append(zone)
    if not normalized:
        raise ValueError("At least one schedule zone is required")
    return tuple(normalized)


class CoreScheduleManager:
    """Core-owned schedule configuration and local-time evaluation."""

    def __init__(
        self,
        store: ScheduleStore,
        *,
        zones: Sequence[str] = DEFAULT_SCHEDULE_ZONES,
        timezone_name: str = SCHEDULE_TIMEZONE,
    ) -> None:
        self._store = store
        self._zones = _normalize_zones(zones)
        ZoneInfo(timezone_name)
        self._timezone_name = timezone_name
        self._lock = RLock()

    @property
    def zones(self) -> tuple[str, ...]:
        return self._zones

    def current_state(self, now_utc: datetime | None = None) -> ScheduleState:
        with self._lock:
            try:
                windows = self._store.list_windows()
                return evaluate_schedule(
                    windows,
                    self._zones,
                    now_utc=now_utc,
                    timezone_name=self._timezone_name,
                )
            except Exception as exc:
                LOGGER.exception("Schedule evaluation failed; exposing UNKNOWN schedule state")
                return unavailable_schedule_state(
                    self._zones,
                    error=str(exc),
                    now_utc=now_utc,
                    timezone_name=self._timezone_name,
                )

    def configuration(self, now_utc: datetime | None = None) -> dict[str, object]:
        with self._lock:
            try:
                windows = self._store.list_windows()
            except Exception as exc:
                state = unavailable_schedule_state(
                    self._zones,
                    error=str(exc),
                    now_utc=now_utc,
                    timezone_name=self._timezone_name,
                )
                return {
                    "available": False,
                    "timezone": self._timezone_name,
                    "zones": list(self._zones),
                    "windows": [],
                    "state": state.to_dict(),
                    "last_error": str(exc),
                }
            state = evaluate_schedule(
                windows,
                self._zones,
                now_utc=now_utc,
                timezone_name=self._timezone_name,
            )
            return {
                "available": True,
                "timezone": self._timezone_name,
                "zones": list(self._zones),
                "windows": [window.to_dict() for window in windows],
                "state": state.to_dict(),
                "last_error": "",
            }

    def replace_zone(self, zone: str, windows: Sequence[ScheduleWindow]) -> dict[str, object]:
        with self._lock:
            if zone not in self._zones:
                raise ValueError(f"Unsupported schedule zone: {zone}")
            window_tuple = tuple(windows)
            if any(window.zone != zone for window in window_tuple):
                raise ValueError("Every replacement window must belong to the selected zone")
            validate_windows(window_tuple)
            self._store.replace_zone(zone, window_tuple)
            return self.configuration()

    def close(self) -> None:
        with self._lock:
            self._store.close()


class UnavailableScheduleManager:
    """Fail-safe schedule facade used when the persistent store cannot open."""

    def __init__(
        self,
        error: str,
        *,
        zones: Sequence[str] = DEFAULT_SCHEDULE_ZONES,
        timezone_name: str = SCHEDULE_TIMEZONE,
    ) -> None:
        self._error = error
        self._zones = _normalize_zones(zones)
        ZoneInfo(timezone_name)
        self._timezone_name = timezone_name

    def current_state(self, now_utc: datetime | None = None) -> ScheduleState:
        return unavailable_schedule_state(
            self._zones,
            error=self._error,
            now_utc=now_utc,
            timezone_name=self._timezone_name,
        )

    def configuration(self, now_utc: datetime | None = None) -> dict[str, object]:
        state = self.current_state(now_utc)
        return {
            "available": False,
            "timezone": self._timezone_name,
            "zones": list(self._zones),
            "windows": [],
            "state": state.to_dict(),
            "last_error": self._error,
        }

    def replace_zone(self, zone: str, windows: Sequence[ScheduleWindow]) -> dict[str, object]:
        del zone, windows
        raise RuntimeError(f"Schedule storage is unavailable: {self._error}")

    def close(self) -> None:
        return
