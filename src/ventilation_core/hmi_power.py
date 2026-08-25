from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOGGER = logging.getLogger(__name__)
DEFAULT_ADB = Path("/usr/bin/adb")
DEFAULT_TARGET = "192.168.1.39:5555"
DEFAULT_TIMEOUT_SECONDS = 1.5
DEFAULT_WEB_PORT = 8088
DEFAULT_WEB_READY_TIMEOUT_SECONDS = 20.0
DEFAULT_WEB_READY_POLL_SECONDS = 0.5
DEFAULT_WEB_READY_REQUEST_TIMEOUT_SECONDS = 0.75
DEFAULT_WEB_SETTLE_SECONDS = 4.5


CommandRunner = Callable[[Sequence[str], float], tuple[int, str]]
WebReadyProbe = Callable[[str, float], bool]


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


def _web_state_probe(url: str, timeout_seconds: float) -> bool:
    request = Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is True and isinstance(payload.get("state"), dict)


def wait_for_web_state_ready(
    *,
    url: str,
    timeout_seconds: float = DEFAULT_WEB_READY_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_WEB_READY_POLL_SECONDS,
    request_timeout_seconds: float = DEFAULT_WEB_READY_REQUEST_TIMEOUT_SECONDS,
    settle_seconds: float = DEFAULT_WEB_SETTLE_SECONDS,
    probe: WebReadyProbe = _web_state_probe,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Wait for authoritative WebGUI state, then allow the HMI watchdog to recover.

    This wait is deliberately best-effort. A timeout returns False; callers may
    still wake the HMI so a WebGUI/core failure cannot hold the panel asleep
    indefinitely. The post-ready settle interval covers the HMI WebView
    communication watchdog recovery window while the screen is still dark.
    """
    if timeout_seconds <= 0:
        raise ValueError("web ready timeout must be > 0")
    if poll_seconds <= 0:
        raise ValueError("web ready poll must be > 0")
    if request_timeout_seconds <= 0:
        raise ValueError("web ready request timeout must be > 0")
    if settle_seconds < 0:
        raise ValueError("web settle seconds must be >= 0")

    deadline = monotonic() + timeout_seconds
    while True:
        if probe(url, request_timeout_seconds):
            LOGGER.warning("WebGUI authoritative state is ready at %s", url)
            if settle_seconds:
                LOGGER.warning(
                    "keeping HMI asleep for %.1f s watchdog recovery window before WAKE",
                    settle_seconds,
                )
                sleeper(settle_seconds)
            return True

        remaining = deadline - monotonic()
        if remaining <= 0:
            LOGGER.warning(
                "WebGUI authoritative state was not ready within %.1f s at %s; "
                "continuing because HMI wake is best-effort",
                timeout_seconds,
                url,
            )
            return False
        sleeper(min(poll_seconds, remaining))


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
        if returncode != 0:
            raise RuntimeError(f"adb connect exit={returncode}: {output or '<no output>'}")

        accepted = {
            f"connected to {self._target}".lower(),
            f"already connected to {self._target}".lower(),
        }
        output_lines = {line.strip().lower() for line in output.splitlines() if line.strip()}
        if not accepted.intersection(output_lines):
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
    parser.add_argument("--wait-web-ready", action="store_true")
    parser.add_argument("--web-port", type=int, default=int(os.getenv("WVC_WEB_PORT", str(DEFAULT_WEB_PORT))))
    parser.add_argument("--web-ready-timeout", type=float, default=DEFAULT_WEB_READY_TIMEOUT_SECONDS)
    parser.add_argument("--web-ready-poll", type=float, default=DEFAULT_WEB_READY_POLL_SECONDS)
    parser.add_argument("--web-ready-request-timeout", type=float, default=DEFAULT_WEB_READY_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--web-settle", type=float, default=DEFAULT_WEB_SETTLE_SECONDS)
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
        if args.action == "wake" and args.wait_web_ready:
            ready_url = f"http://127.0.0.1:{args.web_port}/api/v1/state"
            wait_for_web_state_ready(
                url=ready_url,
                timeout_seconds=args.web_ready_timeout,
                poll_seconds=args.web_ready_poll,
                request_timeout_seconds=args.web_ready_request_timeout,
                settle_seconds=args.web_settle,
            )
        success = controller.sleep(strict=args.strict) if args.action == "sleep" else controller.wake(strict=args.strict)
    except Exception as exc:
        LOGGER.error("HMI %s failed: %s", args.action, exc)
        return 1
    return 0 if success or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
