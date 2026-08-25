from __future__ import annotations

import argparse
import logging
from pathlib import Path
import subprocess
import time
from typing import Callable, Sequence


LOGGER = logging.getLogger(__name__)
DEFAULT_ADB = Path("/usr/bin/adb")
DEFAULT_TARGET = "192.168.1.39:5555"
DEFAULT_TIMEOUT_SECONDS = 1.5


CommandRunner = Callable[[Sequence[str], float], tuple[int, str]]


def _subprocess_runner(command: Sequence[str], timeout_seconds: float) -> tuple[int, str]:
    completed = subprocess.run(
        list(command),
        check=False,
        timeout=timeout_seconds,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.returncode, completed.stdout.strip()


class AdbHmiPowerController:
    """Control the iiyama Android HMI power state over wired ADB/TCP.

    The HMI is explicitly non-safety-critical. Callers may use ``strict=False``
    so an unavailable panel is logged but never blocks CM5 boot/shutdown.

    Hardware POC on TW1025LASC-B3PNR established:
    - Android keyevent 223 -> true sleep,
    - Android keyevent 224 -> wake,
    - wired Ethernet and TCP/5555 remain reachable while sleeping.
    """

    KEYEVENTS = {
        "sleep": "223",
        "wake": "224",
    }

    def __init__(
        self,
        *,
        target: str = DEFAULT_TARGET,
        adb_path: Path = DEFAULT_ADB,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = 1,
        retry_delay_seconds: float = 0.5,
        runner: CommandRunner | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not target or ":" not in target:
            raise ValueError("ADB target must use host:port form")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be >= 0")

        self._target = target
        self._adb_path = Path(adb_path)
        self._timeout_seconds = float(timeout_seconds)
        self._attempts = int(attempts)
        self._retry_delay_seconds = float(retry_delay_seconds)
        self._runner = runner or _subprocess_runner
        self._sleeper = sleeper

    @property
    def target(self) -> str:
        return self._target

    def sleep(self, *, strict: bool = False) -> bool:
        return self._set_state("sleep", strict=strict)

    def wake(self, *, strict: bool = False) -> bool:
        return self._set_state("wake", strict=strict)

    def _set_state(self, action: str, *, strict: bool) -> bool:
        if action not in self.KEYEVENTS:
            raise ValueError(f"unsupported HMI power action: {action}")

        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                self._connect()
                self._send_keyevent(self.KEYEVENTS[action])
                LOGGER.warning(
                    "HMI %s commanded via ADB target=%s attempt=%d/%d",
                    action.upper(),
                    self._target,
                    attempt,
                    self._attempts,
                )
                return True
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "HMI %s attempt %d/%d failed for %s: %s",
                    action.upper(),
                    attempt,
                    self._attempts,
                    self._target,
                    exc,
                )
                if attempt < self._attempts and self._retry_delay_seconds:
                    self._sleeper(self._retry_delay_seconds)

        message = f"HMI {action} unavailable after {self._attempts} attempt(s): {last_error}"
        if strict:
            raise RuntimeError(message) from last_error
        LOGGER.error("%s; continuing because HMI is non-blocking", message)
        return False

    def _connect(self) -> None:
        command = (str(self._adb_path), "connect", self._target)
        returncode, output = self._runner(command, self._timeout_seconds)
        normalized = output.lower()
        if returncode != 0:
            raise RuntimeError(f"adb connect exit={returncode}: {output or '<no output>'}")
        if not (
            normalized.startswith("connected to ")
            or normalized.startswith("already connected to ")
        ):
            raise RuntimeError(f"adb connect did not confirm connection: {output or '<no output>'}")

    def _send_keyevent(self, keyevent: str) -> None:
        command = (
            str(self._adb_path),
            "-s",
            self._target,
            "shell",
            "input",
            "keyevent",
            keyevent,
        )
        returncode, output = self._runner(command, self._timeout_seconds)
        if returncode != 0:
            raise RuntimeError(f"adb keyevent exit={returncode}: {output or '<no output>'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop Ventilation HMI sleep/wake controller")
    parser.add_argument("action", choices=("sleep", "wake"))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--adb", type=Path, default=DEFAULT_ADB)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=0.5)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    controller = AdbHmiPowerController(
        target=args.target,
        adb_path=args.adb,
        timeout_seconds=args.timeout,
        attempts=args.attempts,
        retry_delay_seconds=args.retry_delay,
    )
    try:
        success = controller.sleep(strict=args.strict) if args.action == "sleep" else controller.wake(strict=args.strict)
    except Exception as exc:
        LOGGER.error("HMI %s failed: %s", args.action, exc)
        return 1
    return 0 if success or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
