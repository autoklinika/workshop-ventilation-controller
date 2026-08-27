from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import signal
import socket
import threading
from typing import Any

from ventilation_core.infrastructure.rtc_wake import DEFAULT_WAKEALARM_PATH, SysfsRtcWakeAlarm


LOGGER = logging.getLogger(__name__)
DEFAULT_SOCKET = Path("/run/wvc-rtc/rtc-wake.sock")
MAX_REQUEST_BYTES = 1024


class RtcWakeAgent:
    """Privileged local-only owner of Raspberry Pi RTC wakealarm.

    The protocol is intentionally narrow: read, clear, or arm one absolute UTC
    epoch with mandatory SysfsRtcWakeAlarm read-back verification. It has no
    host-power, shell-command, calendar, or ventilation control path.
    """

    def __init__(self, socket_path: Path, wakealarm_path: Path = DEFAULT_WAKEALARM_PATH) -> None:
        self._socket_path = Path(socket_path)
        self._rtc = SysfsRtcWakeAlarm(Path(wakealarm_path))

    def serve(self, stop_event: threading.Event) -> None:
        parent = self._socket_path.parent
        if not parent.is_dir():
            raise RuntimeError(f"RTC runtime directory does not exist: {parent}")
        if self._socket_path.exists() or self._socket_path.is_symlink():
            self._socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self._socket_path))
            self._socket_path.chmod(0o660)
            server.listen(4)
            server.settimeout(0.5)
            LOGGER.info("RTC wake agent listening on %s", self._socket_path)
            while not stop_event.is_set():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if stop_event.is_set():
                        break
                    raise
                with connection:
                    self._handle_connection(connection)
        finally:
            server.close()
            try:
                self._socket_path.unlink()
            except FileNotFoundError:
                pass

    def _handle_connection(self, connection: socket.socket) -> None:
        connection.settimeout(1.0)
        try:
            payload = self._decode(self._read_request(connection))
            command = payload["command"]
            if command == "read":
                self._send(connection, {"ok": True, "command": "read", "wake_epoch": self._rtc.read_epoch()})
                return
            if command == "clear":
                self._rtc.clear()
                self._send(connection, {"ok": True, "command": "clear", "wake_epoch": self._rtc.read_epoch()})
                return

            wake_epoch = payload["wake_epoch"]
            minimum_lead = payload["minimum_lead_seconds"]
            wake_at = datetime.fromtimestamp(wake_epoch, tz=timezone.utc)
            result = self._rtc.arm(wake_at, minimum_lead_seconds=minimum_lead)
            self._send(
                connection,
                {
                    "ok": True,
                    "command": "arm",
                    "wake_epoch": self._rtc.read_epoch(),
                    "result": result.to_dict(),
                },
            )
        except Exception as exc:
            LOGGER.warning("RTC wake request failed: %s", exc)
            try:
                self._send(connection, {"ok": False, "error": str(exc)})
            except OSError:
                pass

    @staticmethod
    def _decode(raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON request") from exc
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
        command = payload.get("command")
        if command in {"read", "clear"}:
            if set(payload) != {"command"}:
                raise ValueError(f"{command} request must contain only command")
            return payload
        if command != "arm":
            raise ValueError("command must be read, clear or arm")
        if set(payload) != {"command", "wake_epoch", "minimum_lead_seconds"}:
            raise ValueError("arm request has invalid fields")
        wake_epoch = payload.get("wake_epoch")
        minimum_lead = payload.get("minimum_lead_seconds")
        if isinstance(wake_epoch, bool) or not isinstance(wake_epoch, int) or wake_epoch <= 0:
            raise ValueError("wake_epoch must be a positive integer")
        if isinstance(minimum_lead, bool) or not isinstance(minimum_lead, int) or minimum_lead < 1:
            raise ValueError("minimum_lead_seconds must be a positive integer")
        return payload

    @staticmethod
    def _read_request(connection: socket.socket) -> bytes:
        data = bytearray()
        while len(data) < MAX_REQUEST_BYTES:
            chunk = connection.recv(min(256, MAX_REQUEST_BYTES - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
        if not data:
            raise ValueError("empty request")
        if len(data) >= MAX_REQUEST_BYTES and b"\n" not in data:
            raise ValueError("request too large")
        return bytes(data).split(b"\n", 1)[0]

    @staticmethod
    def _send(connection: socket.socket, payload: dict[str, object]) -> None:
        connection.sendall(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop Ventilation privileged RTC wake agent")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--wakealarm", type=Path, default=DEFAULT_WAKEALARM_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop_event = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop_event.set())
    RtcWakeAgent(args.socket, args.wakealarm).serve(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
