from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import signal
import socket
import subprocess
import threading
from typing import Any, Callable


LOGGER = logging.getLogger(__name__)
DEFAULT_SOCKET = Path("/run/wvc-host-power/host-power.sock")
DEFAULT_CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
MAX_REQUEST_BYTES = 1024
MAX_CORE_RESPONSE_BYTES = 1024 * 1024
CORE_REQUEST_TIMEOUT_SECONDS = 75.0


CommandLauncher = Callable[[tuple[str, ...]], None]
CoreRequester = Callable[[dict[str, object]], dict[str, object]]


class HostPowerAgent:
    """Privileged local agent exposing only shutdown/restart over AF_UNIX.

    Shutdown remains fail-closed for local EC outputs. Before host poweroff is
    accepted the agent asks ventilation-core to enter STOP and positively
    confirms both local fan outputs at 0 V with a known output state.

    When AERO is online/usable, airing OFF and speed 0 still require positive
    physical confirmation. When core already reports AERO as offline and
    unusable, the unavailable peripheral cannot be commanded or confirmed, so
    it does not block CM5 host poweroff after the local STOP/0 V checks pass.
    """

    COMMANDS: dict[str, tuple[str, ...]] = {
        "shutdown": ("/usr/bin/systemctl", "--no-block", "poweroff"),
        "restart": ("/usr/bin/systemctl", "--no-block", "reboot"),
    }

    def __init__(
        self,
        socket_path: Path,
        *,
        core_socket_path: Path = DEFAULT_CORE_SOCKET,
        action_delay_seconds: float = 0.75,
        command_launcher: CommandLauncher | None = None,
        core_requester: CoreRequester | None = None,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._core_socket_path = Path(core_socket_path)
        self._action_delay_seconds = float(action_delay_seconds)
        self._command_launcher = command_launcher or self._launch_command
        self._core_requester = core_requester or self._request_core
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

            if action == "shutdown":
                try:
                    self._prepare_peripherals_for_poweroff()
                except Exception as exc:
                    LOGGER.exception("safe peripheral shutdown preparation failed")
                    with self._pending_lock:
                        self._action_pending = False
                    self._send(
                        connection,
                        {
                            "ok": False,
                            "error": f"peripheral shutdown not confirmed: {exc}",
                        },
                    )
                    return

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

    def _prepare_peripherals_for_poweroff(self) -> None:
        LOGGER.warning("preparing ventilation peripherals for CM5 poweroff")

        stop = self._core_requester({"command": "stop"})
        self._require_core_ok(stop, "fan STOP")
        state = stop.get("state")
        if not isinstance(state, dict):
            raise RuntimeError("fan STOP response has no state")
        if state.get("mode") != "STOP":
            raise RuntimeError(f"fan STOP did not enter STOP mode: {state.get('mode')!r}")
        setpoints = state.get("setpoints")
        if not isinstance(setpoints, dict):
            raise RuntimeError("fan STOP response has no setpoints")
        if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
            raise RuntimeError(f"fan outputs are not 0 V: {setpoints!r}")
        if state.get("output_state_known") is not True:
            raise RuntimeError("fan output state is not confirmed")

        if self._aero_is_unavailable(state):
            LOGGER.warning(
                "AERO already offline/unusable before CM5 poweroff; "
                "skipping unavailable AERO shutdown confirmation"
            )
            return

        airing = self._core_requester({"command": "aero-airing", "enabled": False})
        self._require_aero_zero(airing, expected_kind="airing", label="AERO airing OFF")

        speed = self._core_requester({"command": "aero-speed", "speed": 0})
        self._require_aero_zero(speed, expected_kind="speed", label="AERO speed 0")

        LOGGER.warning("all ventilation peripherals confirmed off before CM5 poweroff")

    @staticmethod
    def _aero_is_unavailable(state: dict[str, object]) -> bool:
        aero_bus = state.get("aero_bus")
        if not isinstance(aero_bus, dict):
            return False
        return aero_bus.get("online") is False and aero_bus.get("usable") is False

    @staticmethod
    def _require_core_ok(response: dict[str, object], label: str) -> None:
        if response.get("ok") is not True:
            raise RuntimeError(f"{label} failed: {response.get('error') or response!r}")

    @classmethod
    def _require_aero_zero(
        cls,
        response: dict[str, object],
        *,
        expected_kind: str,
        label: str,
    ) -> None:
        cls._require_core_ok(response, label)
        result = response.get("aero_control")
        if not isinstance(result, dict):
            raise RuntimeError(f"{label} response has no aero_control result")
        if result.get("kind") != expected_kind:
            raise RuntimeError(f"{label} returned unexpected kind: {result.get('kind')!r}")
        if result.get("target_value") != 0:
            raise RuntimeError(f"{label} did not target 0: {result.get('target_value')!r}")
        if result.get("state") != "succeeded":
            raise RuntimeError(f"{label} was not confirmed: {result.get('state')!r}")
        if result.get("physical_confirmation") is not True:
            raise RuntimeError(f"{label} lacks physical confirmation")
        if expected_kind == "speed":
            observed = result.get("observed_power")
            if not isinstance(observed, dict):
                raise RuntimeError("AERO speed 0 response has no observed fan power")
            if observed.get("fan_1_percent") != 0 or observed.get("fan_2_percent") != 0:
                raise RuntimeError(f"AERO fan power is not 0%: {observed!r}")

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

    def _request_core(self, payload: dict[str, object]) -> dict[str, object]:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(CORE_REQUEST_TIMEOUT_SECONDS)
            client.connect(str(self._core_socket_path))
            client.sendall(encoded)
            data = bytearray()
            while len(data) < MAX_CORE_RESPONSE_BYTES:
                chunk = client.recv(min(4096, MAX_CORE_RESPONSE_BYTES - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if b"\n" in chunk:
                    break
        if not data:
            raise RuntimeError("ventilation-core returned an empty response")
        if len(data) >= MAX_CORE_RESPONSE_BYTES and b"\n" not in data:
            raise RuntimeError("ventilation-core response is too large")
        try:
            decoded: Any = json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("ventilation-core returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("ventilation-core returned a non-object response")
        return decoded

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
        subprocess.run(
            command,
            check=True,
            timeout=5.0,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workshop Ventilation CM5 host power agent")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--core-socket", type=Path, default=DEFAULT_CORE_SOCKET)
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
        core_socket_path=args.core_socket,
        action_delay_seconds=args.action_delay,
    )
    try:
        agent.serve(stop_event)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
