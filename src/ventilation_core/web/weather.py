from __future__ import annotations

from pathlib import Path
from typing import Any

from ventilation_core.weather.cache import WeatherCache
from ventilation_core.weather.provider import WeatherError


class FileWeatherProvider:
    """Read-only Web UI adapter for the CM5-owned local weather snapshot."""

    def __init__(self, path: Path) -> None:
        self._cache = WeatherCache(path)

    def get_snapshot(self) -> dict[str, Any]:
        try:
            snapshot = self._cache.load_snapshot()
        except RuntimeError as exc:
            raise WeatherError(str(exc)) from exc
        if snapshot is None:
            return {
                "available": False,
                "configured": True,
                "source": "local-cache",
                "error": "weather snapshot is not available yet",
            }
        snapshot["configured"] = True
        snapshot["source"] = "local-cache"
        return snapshot
