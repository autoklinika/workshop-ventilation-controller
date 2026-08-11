from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from typing import Any


PULSES_PER_REVOLUTION = 3
RPM_PER_HZ = 60.0 / PULSES_PER_REVOLUTION


@dataclass(frozen=True)
class TachoReading:
    frequency_hz: float
    rpm: float
    sample_count: int
    age_seconds: float | None
    valid: bool

    @classmethod
    def stopped(cls, *, age_seconds: float | None = None) -> "TachoReading":
        return cls(
            frequency_hz=0.0,
            rpm=0.0,
            sample_count=0,
            age_seconds=age_seconds,
            valid=False,
        )


@dataclass(frozen=True)
class FanTachoState:
    line_name: str
    line_offset: int | None
    frequency_hz: float
    rpm: float
    sample_count: int
    age_seconds: float | None
    valid: bool

    @classmethod
    def from_reading(
        cls,
        *,
        line_name: str,
        line_offset: int | None,
        reading: TachoReading,
    ) -> "FanTachoState":
        return cls(
            line_name=line_name,
            line_offset=line_offset,
            frequency_hz=reading.frequency_hz,
            rpm=reading.rpm,
            sample_count=reading.sample_count,
            age_seconds=reading.age_seconds,
            valid=reading.valid,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_name": self.line_name,
            "line_offset": self.line_offset,
            "frequency_hz": self.frequency_hz,
            "rpm": self.rpm,
            "sample_count": self.sample_count,
            "age_seconds": self.age_seconds,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class TachoMonitorState:
    chip_path: str
    ready: bool
    worker_alive: bool
    last_error: str | None
    supply: FanTachoState | None
    extract: FanTachoState | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chip_path": self.chip_path,
            "ready": self.ready,
            "worker_alive": self.worker_alive,
            "last_error": self.last_error,
            "supply": None if self.supply is None else self.supply.to_dict(),
            "extract": None if self.extract is None else self.extract.to_dict(),
        }


class TachoEstimator:
    """Estimate fan speed from timestamps of equal-polarity TACHO edges.

    The hardware validation established 3 pulses per revolution, therefore
    RPM = frequency_hz * 20.  The estimator averages recent periods instead
    of counting edges in a long fixed window, which keeps low-speed response
    reasonably fast while suppressing single-period jitter.
    """

    def __init__(
        self,
        *,
        averaging_periods: int = 6,
        timeout_seconds: float = 0.25,
        minimum_period_seconds: float = 0.001,
    ) -> None:
        if averaging_periods < 1:
            raise ValueError("averaging_periods must be at least 1")
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        if minimum_period_seconds <= 0.0:
            raise ValueError("minimum_period_seconds must be positive")
        self._periods: deque[float] = deque(maxlen=averaging_periods)
        self._last_edge: float | None = None
        self._timeout_seconds = timeout_seconds
        self._minimum_period_seconds = minimum_period_seconds

    def add_edge(self, timestamp: float) -> TachoReading:
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")

        if self._last_edge is not None:
            period = timestamp - self._last_edge
            if period <= 0.0:
                raise ValueError("edge timestamps must be strictly increasing")
            if period > self._timeout_seconds:
                self._periods.clear()
                self._last_edge = timestamp
                return TachoReading.stopped(age_seconds=0.0)
            if period >= self._minimum_period_seconds:
                self._periods.append(period)
        self._last_edge = timestamp
        return self.read(timestamp)

    def read(self, now: float) -> TachoReading:
        if not isfinite(now):
            raise ValueError("now must be finite")
        if self._last_edge is None:
            return TachoReading.stopped()

        age = now - self._last_edge
        if age < 0.0:
            raise ValueError("now cannot precede the last edge")
        if age > self._timeout_seconds or not self._periods:
            return TachoReading.stopped(age_seconds=age)

        average_period = sum(self._periods) / len(self._periods)
        frequency_hz = 1.0 / average_period
        return TachoReading(
            frequency_hz=frequency_hz,
            rpm=frequency_hz * RPM_PER_HZ,
            sample_count=len(self._periods),
            age_seconds=age,
            valid=True,
        )

    def reset(self) -> None:
        self._periods.clear()
        self._last_edge = None
