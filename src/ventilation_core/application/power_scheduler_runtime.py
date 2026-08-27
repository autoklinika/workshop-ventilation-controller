from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from threading import Event, Lock, Thread

from ventilation_core.application.power_scheduler import (
    HOST_POWER_REQUEST_FAILED,
    RTC_WAKE_ARM_FAILED,
    HostPowerRequester,
    PowerScheduler,
    PowerSchedulerState,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PowerSchedulerRuntimeSnapshot:
    state: PowerSchedulerState
    worker_alive: bool
    last_tick_at: str | None
    last_attempted_wake_at_utc: str | None
    last_host_power_requested: bool
    last_host_power_accepted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            **self.state.to_dict(),
            "worker_alive": self.worker_alive,
            "last_tick_at": self.last_tick_at,
            "last_attempted_wake_at_utc": self.last_attempted_wake_at_utc,
            "last_host_power_requested": self.last_host_power_requested,
            "last_host_power_accepted": self.last_host_power_accepted,
        }


class PowerSchedulerRuntime:
    """Non-blocking periodic runtime for the Calendar-driven PowerScheduler.

    Status reads never execute anything. The worker owns the only automatic
    execution path and records at most one failed/accepted shutdown attempt per
    next_wake timestamp, preventing repeated power requests on periodic ticks.
    The first automatic tick is deliberately delayed by one poll interval so
    the core Unix server is already available to the host-power safety path.
    """

    def __init__(
        self,
        scheduler: PowerScheduler,
        host_power: HostPowerRequester,
        *,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("power scheduler poll interval must be positive")
        self._scheduler = scheduler
        self._host_power = host_power
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._stop = Event()
        self._lock = Lock()
        self._last_attempted_wake: str | None = None
        self._last_tick_at: str | None = None
        self._last_host_power_requested = False
        self._last_host_power_accepted = False
        self._state = scheduler.diagnostics()
        self._thread = Thread(target=self._run, name="wvc-power-scheduler", daemon=True)
        self._thread.start()

    def snapshot(self) -> PowerSchedulerRuntimeSnapshot:
        with self._lock:
            return PowerSchedulerRuntimeSnapshot(
                state=self._state,
                worker_alive=self._thread.is_alive(),
                last_tick_at=self._last_tick_at,
                last_attempted_wake_at_utc=self._last_attempted_wake,
                last_host_power_requested=self._last_host_power_requested,
                last_host_power_accepted=self._last_host_power_accepted,
            )

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, min(5.0, self._poll_interval_seconds + 0.5)))
        if self._thread.is_alive():
            LOGGER.error("Power Scheduler worker did not stop within bounded timeout")

    def tick_once(self, now_utc: datetime | None = None) -> PowerSchedulerRuntimeSnapshot:
        """Execute one worker iteration; public for deterministic tests only."""
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        planned = self._scheduler.diagnostics(now)
        wake_key = planned.next_wake_at_utc
        host_requested = False
        host_accepted = False
        resulting_state = planned

        with self._lock:
            attempted_wake = self._last_attempted_wake

        should_attempt = (
            self._scheduler.enabled
            and wake_key is not None
            and wake_key != attempted_wake
        )
        if should_attempt:
            execution = self._scheduler.execute_scheduled_shutdown(self._host_power, now)
            resulting_state = execution.state
            host_requested = execution.host_power_requested
            host_accepted = execution.host_power_accepted
            if (
                execution.host_power_requested
                or execution.alert_code in {RTC_WAKE_ARM_FAILED, HOST_POWER_REQUEST_FAILED}
                or execution.state.shutdown_ready is True
            ):
                attempted_wake = wake_key

        with self._lock:
            self._state = resulting_state
            self._last_tick_at = now.isoformat()
            self._last_attempted_wake = attempted_wake
            self._last_host_power_requested = host_requested
            self._last_host_power_accepted = host_accepted
        return self.snapshot()

    def _run(self) -> None:
        if self._stop.wait(self._poll_interval_seconds):
            return
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:
                LOGGER.exception("Power Scheduler runtime tick failed; CM5 remains running")
            if self._stop.wait(self._poll_interval_seconds):
                break
