from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol


DEFAULT_WAKEALARM_PATH = Path("/sys/class/rtc/rtc0/wakealarm")


class RtcWakeArmError(RuntimeError):
    pass


@dataclass(frozen=True)
class RtcWakeArmResult:
    requested_epoch: int
    verified_epoch: int
    requested_at_utc: str
    verified: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_epoch": self.requested_epoch,
            "verified_epoch": self.verified_epoch,
            "requested_at_utc": self.requested_at_utc,
            "verified": self.verified,
        }


class RtcWakeAlarm(Protocol):
    def read_epoch(self) -> int | None: ...
    def clear(self) -> None: ...
    def arm(self, wake_at: datetime, *, minimum_lead_seconds: int = 60) -> RtcWakeArmResult: ...


class SysfsRtcWakeAlarm:
    """Raspberry Pi RTC wakealarm adapter with mandatory read-back verification."""

    def __init__(
        self,
        wakealarm_path: Path = DEFAULT_WAKEALARM_PATH,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(wakealarm_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _read_raw(self) -> str:
        return self._path.read_text(encoding="ascii").strip()

    def _write_raw(self, value: str) -> None:
        self._path.write_text(value + "\n", encoding="ascii")

    def read_epoch(self) -> int | None:
        try:
            raw = self._read_raw()
        except OSError as exc:
            raise RtcWakeArmError(f"cannot read RTC wakealarm {self._path}: {exc}") from exc
        if raw in {"", "0"}:
            return None
        try:
            value = int(raw, 10)
        except ValueError as exc:
            raise RtcWakeArmError(f"RTC wakealarm returned non-integer value: {raw!r}") from exc
        if value <= 0:
            raise RtcWakeArmError(f"RTC wakealarm returned invalid epoch: {value}")
        return value

    def clear(self) -> None:
        try:
            self._write_raw("0")
        except OSError as exc:
            raise RtcWakeArmError(f"cannot clear RTC wakealarm {self._path}: {exc}") from exc
        if self.read_epoch() is not None:
            raise RtcWakeArmError("RTC wakealarm did not clear")

    def arm(self, wake_at: datetime, *, minimum_lead_seconds: int = 60) -> RtcWakeArmResult:
        if isinstance(minimum_lead_seconds, bool) or not isinstance(minimum_lead_seconds, int):
            raise ValueError("minimum_lead_seconds must be an integer")
        if minimum_lead_seconds < 1:
            raise ValueError("minimum_lead_seconds must be positive")
        if wake_at.tzinfo is None or wake_at.utcoffset() is None:
            raise ValueError("RTC wake target must be timezone-aware")

        target_utc = wake_at.astimezone(timezone.utc)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("RTC wake clock returned naive datetime")
        now_utc = now.astimezone(timezone.utc)

        target_epoch = int(target_utc.timestamp())
        now_epoch = int(now_utc.timestamp())
        lead = target_epoch - now_epoch
        if lead < minimum_lead_seconds:
            raise RtcWakeArmError(
                f"RTC wake target is too close or in the past: lead={lead}s, minimum={minimum_lead_seconds}s"
            )

        self.clear()
        try:
            self._write_raw(str(target_epoch))
        except OSError as exc:
            raise RtcWakeArmError(f"cannot arm RTC wakealarm {self._path}: {exc}") from exc

        try:
            verified_epoch = self.read_epoch()
        except Exception:
            self._best_effort_clear()
            raise
        if verified_epoch != target_epoch:
            self._best_effort_clear()
            raise RtcWakeArmError(
                f"RTC wakealarm read-back mismatch: expected={target_epoch}, actual={verified_epoch!r}"
            )

        return RtcWakeArmResult(
            requested_epoch=target_epoch,
            verified_epoch=verified_epoch,
            requested_at_utc=target_utc.isoformat(),
            verified=True,
        )

    def _best_effort_clear(self) -> None:
        try:
            self._write_raw("0")
        except OSError:
            return
