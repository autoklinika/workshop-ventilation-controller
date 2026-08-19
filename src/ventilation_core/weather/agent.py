from __future__ import annotations

import logging
from threading import Event

from .cache import WeatherCache
from .provider import MetNoWeatherClient


LOGGER = logging.getLogger(__name__)


class WeatherAgent:
    """Independent CM5 worker that refreshes the local weather snapshot."""

    def __init__(
        self,
        *,
        client: MetNoWeatherClient,
        cache: WeatherCache,
        poll_interval_seconds: float,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("weather poll interval must be positive")
        self._client = client
        self._cache = cache
        self._poll_interval_seconds = poll_interval_seconds

    def fetch_once(self) -> dict[str, object]:
        snapshot = self._client.fetch_snapshot()
        self._cache.save(snapshot)
        return snapshot

    def run(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            try:
                snapshot = self.fetch_once()
                LOGGER.info(
                    "weather snapshot updated provider=%s location=%s observed_at=%s",
                    snapshot.get("provider"),
                    snapshot.get("location"),
                    snapshot.get("observed_at"),
                )
            except Exception as exc:
                # Never erase a previously good snapshot because the network/provider failed.
                LOGGER.warning("weather refresh failed; keeping last good cache: %s", exc)
            stop_event.wait(self._poll_interval_seconds)
