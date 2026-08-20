from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Any, Callable, Sequence


_THROTTLED_PATTERN = re.compile(r"^throttled=0x([0-9a-fA-F]+)$")
_UNDERVOLTAGE_NOW_BIT = 1 << 0
_UNDERVOLTAGE_OCCURRED_BIT = 1 << 16


@dataclass(frozen=True)
class SystemPowerState:
    available: bool
    undervoltage_now: bool | None
    undervoltage_occurred: bool | None
    throttled_mask: int | None
    consecutive_failures: int = 0
    last_error: str | None = None


class RaspberryPiSystemPowerMonitor:
    """Read Raspberry Pi firmware power flags without changing system state.

    The monitor uses ``vcgencmd get_throttled``. Bit 0 is the authoritative
    *current* under-voltage indication used for the active alert lifecycle.
    Bit 16 is retained only as diagnostic context because it is latched for the
    current boot and therefore must not keep an alert active indefinitely.

    If a read fails after an active under-voltage observation, the last active
    state is retained until a successful read proves that voltage is normal.
    This avoids clearing a power alert merely because the diagnostic command
    temporarily became unavailable.
    """

    def __init__(
        self,
        *,
        command: Sequence[str] = ("/usr/bin/vcgencmd", "get_throttled"),
        timeout_seconds: float = 0.5,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        if not command:
            raise ValueError("system power command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("system power command timeout must be positive")
        self._command = tuple(str(part) for part in command)
        self._timeout_seconds = float(timeout_seconds)
        self._runner = runner
        self._state = SystemPowerState(
            available=False,
            undervoltage_now=None,
            undervoltage_occurred=None,
            throttled_mask=None,
        )

    def state(self) -> SystemPowerState:
        return self._state

    def poll(self) -> SystemPowerState:
        previous = self._state
        try:
            completed = self._runner(
                self._command,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
            returncode = int(getattr(completed, "returncode", 1))
            stdout = str(getattr(completed, "stdout", "") or "").strip()
            stderr = str(getattr(completed, "stderr", "") or "").strip()
            if returncode != 0:
                detail = stderr or stdout or f"exit status {returncode}"
                raise RuntimeError(f"vcgencmd failed: {detail}")
            mask = self.parse_throttled_mask(stdout)
        except Exception as exc:
            # Keep a previously observed active under-voltage condition latched
            # until a successful read can explicitly clear it.
            retained_active = True if previous.undervoltage_now is True else None
            self._state = SystemPowerState(
                available=False,
                undervoltage_now=retained_active,
                undervoltage_occurred=previous.undervoltage_occurred,
                throttled_mask=previous.throttled_mask,
                consecutive_failures=previous.consecutive_failures + 1,
                last_error=str(exc),
            )
            return self._state

        self._state = SystemPowerState(
            available=True,
            undervoltage_now=bool(mask & _UNDERVOLTAGE_NOW_BIT),
            undervoltage_occurred=bool(mask & _UNDERVOLTAGE_OCCURRED_BIT),
            throttled_mask=mask,
            consecutive_failures=0,
            last_error=None,
        )
        return self._state

    def close(self) -> None:
        return

    @staticmethod
    def parse_throttled_mask(output: str) -> int:
        match = _THROTTLED_PATTERN.fullmatch(output.strip())
        if match is None:
            raise ValueError(f"unexpected vcgencmd get_throttled output: {output!r}")
        return int(match.group(1), 16)
