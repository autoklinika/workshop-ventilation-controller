from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable

from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState


class TachoFeedbackStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    HEALTHY = "HEALTHY"
    CONFIRMING = "CONFIRMING"
    CONFIRMATION_TUNING_REQUIRED = "CONFIRMATION_TUNING_REQUIRED"
    FEEDBACK_MISSING_CONFIRMED = "FEEDBACK_MISSING_CONFIRMED"
    MONITOR_UNAVAILABLE = "MONITOR_UNAVAILABLE"
    CHANNEL_UNAVAILABLE = "CHANNEL_UNAVAILABLE"


@dataclass(frozen=True)
class TachoChannelSupervision:
    channel: str
    command_voltage: float
    feedback_required: bool
    status: TachoFeedbackStatus
    feedback_valid: bool
    rpm: float | None
    age_seconds: float | None
    confirmation_seconds: float | None
    pending_since_utc: str | None
    fault_confirmed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "command_voltage": self.command_voltage,
            "feedback_required": self.feedback_required,
            "status": self.status.value,
            "feedback_valid": self.feedback_valid,
            "rpm": self.rpm,
            "age_seconds": self.age_seconds,
            "confirmation_seconds": self.confirmation_seconds,
            "pending_since_utc": self.pending_since_utc,
            "fault_confirmed": self.fault_confirmed,
        }


class TachoSupervisionTracker:
    """Stateful supervision of feedback only when a physical fan is commanded on.

    `FanTachoState.valid == False` is normal at 0 V and must never be classified as
    a feedback failure. A non-zero physical command arms supervision. Missing
    pulses are confirmed only after an explicit configured confirmation interval,
    which also serves as the spin-up allowance. No emergency actuator policy lives
    in this tracker.
    """

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._pending_since: dict[str, datetime | None] = {
            "supply": None,
            "extract": None,
        }

    def evaluate(
        self,
        *,
        monitor: TachoMonitorState | None,
        supply_voltage: float,
        extract_voltage: float,
        confirmation_seconds: float | None,
    ) -> tuple[TachoChannelSupervision, TachoChannelSupervision]:
        if confirmation_seconds is not None and confirmation_seconds < 0.0:
            raise ValueError("TACHO confirmation_seconds must be non-negative")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("TACHO supervision clock must be timezone-aware")

        supply = self._channel(
            channel="supply",
            command_voltage=float(supply_voltage),
            monitor=monitor,
            feedback=None if monitor is None else monitor.supply,
            confirmation_seconds=confirmation_seconds,
            now=now,
        )
        extract = self._channel(
            channel="extract",
            command_voltage=float(extract_voltage),
            monitor=monitor,
            feedback=None if monitor is None else monitor.extract,
            confirmation_seconds=confirmation_seconds,
            now=now,
        )
        return supply, extract

    def _channel(
        self,
        *,
        channel: str,
        command_voltage: float,
        monitor: TachoMonitorState | None,
        feedback: FanTachoState | None,
        confirmation_seconds: float | None,
        now: datetime,
    ) -> TachoChannelSupervision:
        required = command_voltage > 0.0
        if not required:
            self._pending_since[channel] = None
            return TachoChannelSupervision(
                channel=channel,
                command_voltage=command_voltage,
                feedback_required=False,
                status=TachoFeedbackStatus.NOT_REQUIRED,
                feedback_valid=False if feedback is None else feedback.valid,
                rpm=None if feedback is None else feedback.rpm,
                age_seconds=None if feedback is None else feedback.age_seconds,
                confirmation_seconds=confirmation_seconds,
                pending_since_utc=None,
                fault_confirmed=False,
            )

        if monitor is None or not monitor.ready or not monitor.worker_alive:
            self._pending_since[channel] = None
            return TachoChannelSupervision(
                channel=channel,
                command_voltage=command_voltage,
                feedback_required=True,
                status=TachoFeedbackStatus.MONITOR_UNAVAILABLE,
                feedback_valid=False,
                rpm=None if feedback is None else feedback.rpm,
                age_seconds=None if feedback is None else feedback.age_seconds,
                confirmation_seconds=confirmation_seconds,
                pending_since_utc=None,
                fault_confirmed=True,
            )

        if feedback is None:
            self._pending_since[channel] = None
            return TachoChannelSupervision(
                channel=channel,
                command_voltage=command_voltage,
                feedback_required=True,
                status=TachoFeedbackStatus.CHANNEL_UNAVAILABLE,
                feedback_valid=False,
                rpm=None,
                age_seconds=None,
                confirmation_seconds=confirmation_seconds,
                pending_since_utc=None,
                fault_confirmed=True,
            )

        if feedback.valid:
            self._pending_since[channel] = None
            return TachoChannelSupervision(
                channel=channel,
                command_voltage=command_voltage,
                feedback_required=True,
                status=TachoFeedbackStatus.HEALTHY,
                feedback_valid=True,
                rpm=feedback.rpm,
                age_seconds=feedback.age_seconds,
                confirmation_seconds=confirmation_seconds,
                pending_since_utc=None,
                fault_confirmed=False,
            )

        if confirmation_seconds is None:
            self._pending_since[channel] = None
            return TachoChannelSupervision(
                channel=channel,
                command_voltage=command_voltage,
                feedback_required=True,
                status=TachoFeedbackStatus.CONFIRMATION_TUNING_REQUIRED,
                feedback_valid=False,
                rpm=feedback.rpm,
                age_seconds=feedback.age_seconds,
                confirmation_seconds=None,
                pending_since_utc=None,
                fault_confirmed=False,
            )

        pending = self._pending_since[channel]
        if pending is None:
            pending = now
            self._pending_since[channel] = pending
        elapsed = max(0.0, (now - pending).total_seconds())
        confirmed = elapsed >= confirmation_seconds
        return TachoChannelSupervision(
            channel=channel,
            command_voltage=command_voltage,
            feedback_required=True,
            status=(
                TachoFeedbackStatus.FEEDBACK_MISSING_CONFIRMED
                if confirmed
                else TachoFeedbackStatus.CONFIRMING
            ),
            feedback_valid=False,
            rpm=feedback.rpm,
            age_seconds=feedback.age_seconds,
            confirmation_seconds=confirmation_seconds,
            pending_since_utc=pending.isoformat(),
            fault_confirmed=confirmed,
        )
