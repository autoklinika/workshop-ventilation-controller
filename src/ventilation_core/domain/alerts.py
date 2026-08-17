from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ventilation_core.domain.models import AlarmCode, AlarmSeverity, AlarmState


@dataclass(frozen=True)
class AlertSignal:
    """Current alarm condition detected by ventilation-core.

    ``key`` identifies one independently active condition.  ``code`` classifies
    the condition, while ``source`` distinguishes instances such as individual
    SEN55 nodes.
    """

    key: str
    code: AlarmCode
    source: str
    severity: AlarmSeverity
    message: str
    detail: str = ""
    occurrences: int = 1

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("Alert key cannot be empty")
        if not self.source:
            raise ValueError("Alert source cannot be empty")
        if not self.message:
            raise ValueError("Alert message cannot be empty")
        if self.occurrences < 1:
            raise ValueError("Alert occurrences must be at least 1")


@dataclass(frozen=True)
class AlertRecord:
    alert_id: int
    key: str
    code: AlarmCode
    source: str
    severity: AlarmSeverity
    message: str
    detail: str
    active_since: str
    acknowledged_at: str | None
    cleared_at: str | None
    occurrences: int

    @property
    def active(self) -> bool:
        return self.cleared_at is None

    @property
    def acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    def to_alarm_state(self) -> AlarmState:
        return AlarmState(
            code=self.code,
            severity=self.severity,
            message=self.message,
            active_since=self.active_since,
            last_error=self.detail,
            occurrences=self.occurrences,
            alert_id=self.alert_id,
            source=self.source,
            acknowledged_at=self.acknowledged_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "key": self.key,
            "code": self.code.value,
            "source": self.source,
            "severity": self.severity.value,
            "message": self.message,
            "detail": self.detail,
            "active_since": self.active_since,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at,
            "active": self.active,
            "cleared_at": self.cleared_at,
            "occurrences": self.occurrences,
        }
