from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
from typing import Callable


LOGGER = logging.getLogger(__name__)
DEFAULT_SOCKET = Path("/run/wvc-host-power/host-power.sock")
MAX_REQUEST_BYTES = 1024


CommandLauncher = Callable[[tuple[str, ...]], None]


class HostPowerAgent:
    """Privileged local agent exposing only shutdown/restart over AF_UNIX."""

    COMMANDS: dict[str, tuple[str, ...]] = {
        "shutdown": ("/usr/bin/systemctl", "poweroff"),
        "restart": ("/usr/bin/systemctl", "reboot"),
    }

    def __init__(
        self,
        socket_path: Path,
        *,
        action_delay_seconds: float = 0.75,
        command_launcher: CommandLauncher | None = None,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._action_delay_seconds = float(action_delay_seconds)
        self._command_launcher = command_launcher or self._launch_command
        self._pending_lock = threading.Lock()
        self._action_pending = False

    def serve(self, stop_event: threading.Event) -> None:
        self._prepare_socket_parent()
        if self._socket_path.exists() or self._socket_path.is_symlink():
            self._socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self._socket_path))
            self._socket_path.chmod(0o660)
            server.listen(4)
            server.settimeout(0.5)
            LOGGER.info("host-power agent listening on %s", self._socket_path)

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

    def _prepare_socket_parent(self) -> None:
        parent = self._socket_path.parent
        if not parent.is_dir():
            raise RuntimeError(f"host-power runtime directory does not exist: {parent}")

    def _handle_connection(self, connection: socket.socket) -> None:
        connection.settimeout(1.0)
        try:
            raw = self._read_request(connection)
            action = self._decode_action(raw)
            with self._pending_lock:
                if self._action_pending:
                    self._send(connection, {"ok": False, "error": "host power action already pending"})
                    return
                self._action_pending = True

            self._send(connection, {"ok": True, "accepted": True, "action": action})
            timer = threading.Timer(
                self._action_delay_seconds,
                self._execute_action,
                args=(action,),
            )
            timer.daemon = True
            timer.start()
        except ValueError as exc:
            self._send(connection, {"ok": False, "error": str(exc)})
        except (OSError, TimeoutError) as exc:
            LOGGER.warning("host-power request failed: %s", exc)

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

    @classmethod
    def _decode_action(cls, raw: bytes) -> str:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON request") from exc
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
        if set(payload) != {"action"}:
            raise ValueError("request must contain only action")
        action = payload.get("action")
        if action not in cls.COMMANDS:
            raise ValueError("action must be shutdown or restart")
        return str(action)

    @staticmethod
    def _send(connection: socket.socket, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        connection.sendall(encoded)

    def _execute_action(self, action: str) -> None:
        command = self.COMMANDS[action]
        LOGGER.warning("executing CM5 host power action: %s", action)
        try:
            self._command_launcher(command)
        except Exception:
            LOGGER.exception("unable to execute host power action: %s", action)
            with self._pending_lock:
                self._action_pending = False

    @staticmethod
    def _launch_command(command: tuple[str, ...]) -> None:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop Ventilation CM5 host power agent")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--action-delay", type=float, default=0.75)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop_event = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, request_stop)

    agent = HostPowerAgent(
        args.socket,
        action_delay_seconds=args.action_delay,
    )
    try:
        agent.serve(stop_event)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
