from __future__ import annotations

import logging
from threading import Event

from .cache import AdvisoryCache
from .client import AIBridgeAdvisoryClient


LOGGER = logging.getLogger(__name__)


class AdvisoryAgent:
    """Poll AI Bridge independently from all ventilation control loops."""

    def __init__(
        self,
        *,
        client: AIBridgeAdvisoryClient,
        cache: AdvisoryCache,
        source_id: str,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.client = client
        self.cache = cache
        self.source_id = source_id
        self.poll_interval_seconds = poll_interval_seconds

    def fetch_once(self) -> bool:
        report = self.client.fetch_latest(self.source_id)
        if report is None:
            LOGGER.info("No AI advisory analysis is available yet source_id=%s", self.source_id)
            return False

        analysis_id = report["analysis_id"]
        try:
            current_analysis_id = self.cache.current_analysis_id()
        except RuntimeError as exc:
            # A bad advisory cache must not become a permanent failure state.
            # A freshly validated remote report can safely replace it atomically.
            LOGGER.warning("Existing AI advisory cache is invalid and will be replaced: %s", exc)
            current_analysis_id = None

        if current_analysis_id == analysis_id:
            LOGGER.debug("AI advisory unchanged analysis_id=%s", analysis_id)
            return False

        self.cache.save(report)
        LOGGER.info(
            "AI advisory cached analysis_id=%s source_id=%s window=%s..%s status=%s",
            analysis_id,
            self.source_id,
            report["window_start"],
            report["window_end"],
            report["result"]["status"],
        )
        return True

    def run(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            try:
                self.fetch_once()
            except Exception as exc:  # network/storage errors must never stop ventilation
                LOGGER.warning("AI advisory refresh failed: %s", exc)
            stop_event.wait(self.poll_interval_seconds)
