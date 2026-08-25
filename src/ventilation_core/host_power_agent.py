from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
from typing import Any, Callable

from ventilation_core.power_domain import Dfr0473PowerDomain, PowerDomain


LOGGER = logging.getLogger(__name__)
DEFAULT_SOCKET = Path("/run/wvc-host-power/host-power.sock")
DEFAULT_CORE_SOCKET = Path("/run/workshop-ventilation/ventilation-core.sock")
MAX_REQUEST_BYTES = 1024
MAX_CORE_RESPONSE_BYTES = 1024 * 1024
CORE_REQUEST_TIMEOUT_SECONDS = 10.0


CommandLauncher = Callable[[tuple[str, ...]], None]
CoreRequester = Callable[[dict[str, object]], dict[str, object]]
ReadyNotifier = Callable[[str], None]


def notify_systemd_ready(status: str) -> None:
    """Send READY=1 to systemd without adding a python-systemd dependency."""
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return

    address: str | bytes
    if notify_socket.startswith("@"):
        address = b"\0" + notify_socket[1:].encode()
    else:
        address = notify_socket

    payload = f"READY=1\nSTATUS={status}".encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.connect(address)
        client.sendall(payload)


class HostPowerAgent:
    """Privileged local agent for controlled CM5 shutdown/restart.

    Both normal shutdown and restart follow the same ordering:

    1. attempt local EC STOP / 0 V,
    2. make best-effort shutdown requests to communication peripherals,
    3. command the DFR0473-controlled 12 V domain OFF,
    4. launch the fixed systemd power action.

    A failed or unconfirmed local DAC STOP is a critical diagnostic condition,
    but it must not make host shutdown impossible. The host-power path is the
    final escape path from a failed actuator/control stack. Communication
    failures of AERO or other peripherals are also diagnostic only.

    Failure to command the dedicated DFR0473 12 V isolation relay OFF still
    rejects the normal host power action because that would knowingly leave the
    switched peripheral power domain energized after the CM5 goes down.
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
        power_domain: PowerDomain | None = None,
        ready_notifier: ReadyNotifier | None = None,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._core_socket_path = Path(core_socket_path)
        self._action_delay_seconds = float(action_delay_seconds)
        self._command_launcher = command_launcher or self._launch_command
        self._core_requester = core_requester or self._request_core
        self._power_domain = power_domain
        self._ready_notifier = ready_notifier or notify_systemd_ready
        self._pending_lock = threading.Lock()
        self._action_pending = False

    def serve(self, stop_event: threading.Event) -> None:
        self._prepare_socket_parent()
        if self._socket_path.exists() or self._socket_path.is_symlink():
            self._socket_path.unlink()

        power_domain_started = False
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if self._power_domain is not None:
                self._power_domain.start()
                power_domain_started = True

            server.bind(str(self._socket_path))
            self._socket_path.chmod(0o660)
            server.listen(4)
            server.settimeout(0.5)
            self._ready_notifier("12 V domain ON; host-power agent ready")
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
            if power_domain_started and self._power_domain is not None:
                self._power_domain.close()

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

            try:
                self._prepare_for_host_power_action()
            except Exception as exc:
                LOGGER.exception("safe host power preparation failed")
                with self._pending_lock:
                    self._action_pending = False
                self._send(
                    connection,
                    {
                        "ok": False,
                        "error": f"host power preparation failed: {exc}",
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

    def _prepare_for_host_power_action(self) -> None:
        self._prepare_peripherals_for_poweroff()
        if self._power_domain is not None:
            self._power_domain.power_off()

    def _prepare_peripherals_for_poweroff(self) -> None:
        LOGGER.warning("preparing ventilation outputs for CM5 host power action")

        state: dict[str, object] | None = None
        local_stop_confirmed = False
        try:
            stop = self._core_requester({"command": "stop"})
            self._require_core_ok(stop, "fan STOP")
            candidate = stop.get("state")
            if not isinstance(candidate, dict):
                raise RuntimeError("fan STOP response has no state")
            self._require_local_zero(candidate)
            state = candidate
            local_stop_confirmed = True
            LOGGER.warning("local EC STOP / 0 V confirmed")
        except Exception as exc:
            LOGGER.error(
                "CRITICAL: local EC STOP / 0 V was not confirmed (%s); "
                "continuing host shutdown because actuator communication/state "
                "must not make the system impossible to power off",
                exc,
            )
            state = self._best_effort_core_state()

        if state is not None and self._aero_is_unavailable(state):
            LOGGER.warning(
                "AERO already offline/unusable before host power action; "
                "continuing to 12 V isolation"
            )
            return

        self._best_effort_aero_zero(
            {"command": "aero-airing", "enabled": False},
            expected_kind="airing",
            label="AERO airing OFF",
        )
        self._best_effort_aero_zero(
            {"command": "aero-speed", "speed": 0},
            expected_kind="speed",
            label="AERO speed 0",
        )

        LOGGER.warning(
            "peripheral shutdown attempts completed; local_stop_confirmed=%s",
            local_stop_confirmed,
        )

    def _best_effort_core_state(self) -> dict[str, object] | None:
        try:
            response = self._core_requester({"command": "status"})
            self._require_core_ok(response, "core status after failed STOP")
            state = response.get("state")
            if isinstance(state, dict):
                return state
            LOGGER.warning("core status after failed STOP has no state object")
        except Exception as exc:
            LOGGER.warning("core status unavailable after failed STOP: %s", exc)
        return None

    @staticmethod
    def _require_local_zero(state: dict[str, object]) -> None:
        if state.get("mode") != "STOP":
            raise RuntimeError(f"fan STOP did not enter STOP mode: {state.get('mode')!r}")
        setpoints = state.get("setpoints")
        if not isinstance(setpoints, dict):
            raise RuntimeError("fan STOP response has no setpoints")
        if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
            raise RuntimeError(f"fan outputs are not 0 V: {setpoints!r}")
        if state.get("output_state_known") is not True:
            raise RuntimeError("fan output state is not confirmed")

    def _best_effort_aero_zero(
        self,
        payload: dict[str, object],
        *,
        expected_kind: str,
        label: str,
    ) -> None:
        try:
            response = self._core_requester(payload)
            self._require_aero_zero(
                response,
                expected_kind=expected_kind,
                label=label,
            )
        except Exception as exc:
            LOGGER.warning(
                "%s not confirmed (%s); continuing because peripheral "
                "communication must not block 12 V isolation",
                label,
                exc,
            )

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
    parser.add_argument("--power-domain-chip", default="/dev/gpiochip0")
    parser.add_argument("--power-domain-line", default="GPIO22")
    parser.add_argument("--power-domain-stabilization", type=float, default=1.0)
    parser.add_argument("--disable-power-domain", action="store_true")
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

    power_domain: PowerDomain | None = None
    if not args.disable_power_domain:
        power_domain = Dfr0473PowerDomain(
            chip_path=args.power_domain_chip,
            line_name=args.power_domain_line,
            stabilization_seconds=args.power_domain_stabilization,
        )

    agent = HostPowerAgent(
        args.socket,
        core_socket_path=args.core_socket,
        action_delay_seconds=args.action_delay,
        power_domain=power_domain,
    )
    try:
        agent.serve(stop_event)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
