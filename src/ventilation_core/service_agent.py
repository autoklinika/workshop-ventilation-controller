from __future__ import annotations

import argparse
import json
import logging
import os
import selectors
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from ventilation_core.service_heartbeat import (
    DEFAULT_PORT,
    MAX_DATAGRAM_BYTES,
    HeartbeatError,
    HeartbeatReceiver,
    NodeKey,
    load_node_keys,
)

LOGGER = logging.getLogger("wvc.service_agent")
DEFAULT_BIND_ADDRESS = "10.55.0.1"
DEFAULT_SOCKET_PATH = Path("/run/wvc-service-agent/service-agent.sock")
DEFAULT_RUNTIME_DIR = Path("/run/wvc-service-agent")
DEFAULT_STATE_DIR = Path("/var/lib/wvc-service-heartbeat")
DEFAULT_KEYS_PATH = Path("/etc/wvc-service-heartbeat/keys.json")
MAX_REQUEST_BYTES = 16 * 1024


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


@dataclass(frozen=True)
class ServiceNetworkState:
    interface: str
    profile: str
    bind_address: str
    ap_active: bool
    address_present: bool
    dhcp_active: bool
    firewall_active: bool
    checked_unix_ms: int

    @property
    def ready(self) -> bool:
        return (
            self.ap_active
            and self.address_present
            and self.dhcp_active
            and self.firewall_active
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "interface": self.interface,
            "profile": self.profile,
            "bind_address": self.bind_address,
            "ap_active": self.ap_active,
            "address_present": self.address_present,
            "dhcp_active": self.dhcp_active,
            "firewall_active": self.firewall_active,
            "checked_unix_ms": self.checked_unix_ms,
        }


def _atomic_write_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_command(command: tuple[str, ...]) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return CommandResult(1, "")
    return CommandResult(completed.returncode, completed.stdout.strip())


def probe_service_network(
    command_runner: Callable[[tuple[str, ...]], CommandResult] = run_command,
    *,
    interface: str = "wlan0",
    profile: str = "wvc-sensor-service",
    bind_address: str = DEFAULT_BIND_ADDRESS,
) -> ServiceNetworkState:
    connection = command_runner(
        ("nmcli", "-g", "GENERAL.CONNECTION", "device", "show", interface)
    )
    state = command_runner(("nmcli", "-g", "GENERAL.STATE", "device", "show", interface))
    addresses = command_runner(("nmcli", "-g", "IP4.ADDRESS", "device", "show", interface))
    dhcp = command_runner(("systemctl", "is-active", "wvc-sensor-dhcp.service"))
    firewall = command_runner(("systemctl", "is-active", "wvc-sensor-firewall.service"))

    ap_active = (
        connection.returncode == 0
        and connection.stdout == profile
        and state.returncode == 0
        and state.stdout.startswith("100")
    )
    address_present = (
        addresses.returncode == 0
        and any(
            address.strip().split("/", 1)[0] == bind_address
            for address in addresses.stdout.splitlines()
            if address.strip()
        )
    )
    return ServiceNetworkState(
        interface=interface,
        profile=profile,
        bind_address=bind_address,
        ap_active=ap_active,
        address_present=address_present,
        dhcp_active=dhcp.returncode == 0 and dhcp.stdout == "active",
        firewall_active=firewall.returncode == 0 and firewall.stdout == "active",
        checked_unix_ms=int(time.time() * 1000),
    )


class ServiceAgentState:
    _DIAGNOSTIC_DEFAULTS: dict[str, Any] = {
        "accepted_heartbeats": 0,
        "online_transitions": 0,
        "offline_transitions": 0,
        "boot_changes": 0,
        "sequence_gap_events": 0,
        "missing_heartbeats_total": 0,
        "max_sequence_gap": 0,
        "last_sequence_gap": 0,
        "last_receive_gap_ms": None,
        "max_receive_gap_ms": 0,
        "last_boot_id": None,
        "last_seq": None,
        "last_received_unix_ms": None,
        "last_offline_unix_ms": None,
    }

    def __init__(
        self,
        keys: dict[str, NodeKey],
        *,
        state_dir: Path | None = None,
    ) -> None:
        self._keys = keys
        self._state_dir = state_dir
        self._nodes: dict[str, dict[str, Any]] = {
            node_id: {
                "online": False,
                "received_unix_ms": None,
                "source_ip": None,
                "heartbeat": None,
            }
            for node_id in keys
        }
        self._diagnostics: dict[str, dict[str, Any]] = {
            node_id: self._load_diagnostics(node_id) for node_id in keys
        }

    def _diagnostics_path(self, node_id: str) -> Path | None:
        if self._state_dir is None:
            return None
        return self._state_dir / "diagnostics" / f"{node_id}.json"

    def _load_diagnostics(self, node_id: str) -> dict[str, Any]:
        diagnostics = dict(self._DIAGNOSTIC_DEFAULTS)
        path = self._diagnostics_path(node_id)
        if path is None:
            return diagnostics
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return diagnostics
        if not isinstance(loaded, dict):
            return diagnostics
        for key in diagnostics:
            if key in loaded:
                diagnostics[key] = loaded[key]
        return diagnostics

    def _persist_diagnostics(self, node_id: str) -> None:
        path = self._diagnostics_path(node_id)
        if path is None:
            return
        _atomic_write_json(path, self._diagnostics[node_id])

    def record(self, persisted: dict[str, Any]) -> None:
        heartbeat = persisted.get("heartbeat")
        if not isinstance(heartbeat, dict):
            raise ValueError("persisted heartbeat is missing")
        node_id = heartbeat.get("node_id")
        if node_id not in self._keys:
            raise ValueError("persisted heartbeat belongs to an unknown node")

        previous = self._nodes[node_id]
        diagnostics = self._diagnostics[node_id]
        received_unix_ms = persisted.get("received_unix_ms")
        boot_id = heartbeat.get("boot_id")
        sequence = heartbeat.get("seq")

        diagnostics["accepted_heartbeats"] = int(diagnostics["accepted_heartbeats"]) + 1
        if not bool(previous.get("online")):
            diagnostics["online_transitions"] = int(diagnostics["online_transitions"]) + 1

        previous_received = diagnostics.get("last_received_unix_ms")
        receive_gap_ms: int | None = None
        if isinstance(previous_received, int) and isinstance(received_unix_ms, int):
            receive_gap_ms = max(0, received_unix_ms - previous_received)
            diagnostics["last_receive_gap_ms"] = receive_gap_ms
            diagnostics["max_receive_gap_ms"] = max(
                int(diagnostics["max_receive_gap_ms"]),
                receive_gap_ms,
            )
        if isinstance(received_unix_ms, int):
            diagnostics["last_received_unix_ms"] = received_unix_ms

        previous_boot_id = diagnostics.get("last_boot_id")
        previous_sequence = diagnostics.get("last_seq")
        sequence_gap = 0
        if isinstance(boot_id, str) and isinstance(sequence, int):
            if previous_boot_id == boot_id and isinstance(previous_sequence, int):
                sequence_gap = max(0, sequence - previous_sequence - 1)
                diagnostics["last_sequence_gap"] = sequence_gap
                if sequence_gap > 0:
                    diagnostics["sequence_gap_events"] = (
                        int(diagnostics["sequence_gap_events"]) + 1
                    )
                    diagnostics["missing_heartbeats_total"] = (
                        int(diagnostics["missing_heartbeats_total"]) + sequence_gap
                    )
                    diagnostics["max_sequence_gap"] = max(
                        int(diagnostics["max_sequence_gap"]),
                        sequence_gap,
                    )
                    LOGGER.warning(
                        "node=%s heartbeat sequence gap previous=%d current=%d missing=%d receive_gap_ms=%s",
                        node_id,
                        previous_sequence,
                        sequence,
                        sequence_gap,
                        receive_gap_ms,
                    )
            elif previous_boot_id is not None and previous_boot_id != boot_id:
                diagnostics["boot_changes"] = int(diagnostics["boot_changes"]) + 1
                diagnostics["last_sequence_gap"] = 0
                LOGGER.warning(
                    "node=%s heartbeat boot changed previous=%s current=%s",
                    node_id,
                    previous_boot_id,
                    boot_id,
                )
            else:
                diagnostics["last_sequence_gap"] = 0
            diagnostics["last_boot_id"] = boot_id
            diagnostics["last_seq"] = sequence

        self._nodes[node_id] = dict(persisted)
        self._persist_diagnostics(node_id)

    def mark_offline(self, node_ids: Iterable[str]) -> None:
        for node_id in node_ids:
            current = self._nodes.get(node_id)
            if current is None:
                continue
            diagnostics = self._diagnostics[node_id]
            if bool(current.get("online")):
                diagnostics["offline_transitions"] = (
                    int(diagnostics["offline_transitions"]) + 1
                )
                diagnostics["last_offline_unix_ms"] = int(time.time() * 1000)
                self._persist_diagnostics(node_id)
            current = dict(current)
            current["online"] = False
            current["source_ip"] = None
            self._nodes[node_id] = current

    def nodes(self) -> list[dict[str, Any]]:
        return [self._normalise_node(node_id) for node_id in sorted(self._keys)]

    def _normalise_node(self, node_id: str) -> dict[str, Any]:
        persisted = self._nodes[node_id]
        heartbeat = persisted.get("heartbeat")
        payload = heartbeat if isinstance(heartbeat, dict) else {}
        modbus_address = payload.get("modbus_address")
        if modbus_address is None:
            modbus_address = payload.get("modbus_slave_address")
        if modbus_address is None:
            modbus_address = payload.get("modbus_slave")
        return {
            "node_id": node_id,
            "key_id": self._keys[node_id].key_id,
            "online": bool(persisted.get("online")),
            "received_unix_ms": persisted.get("received_unix_ms"),
            "source_ip": persisted.get("source_ip"),
            "mac": payload.get("mac"),
            "firmware": payload.get("firmware"),
            "uptime_s": payload.get("uptime_s"),
            "wifi_rssi_dbm": payload.get("wifi_rssi_dbm"),
            "sensor_state": payload.get("sensor_state"),
            "measurement_age_ms": payload.get("measurement_age_ms"),
            "rs485_ready": payload.get("rs485_ready"),
            "modbus_monitor_ready": payload.get("modbus_monitor_ready"),
            "modbus_address": modbus_address,
            "modbus_requests_total": payload.get("modbus_requests_total"),
            "modbus_requests_last_60s": payload.get("modbus_requests_last_60s"),
            "last_modbus_request_age_ms": payload.get("last_modbus_request_age_ms"),
            "ota_partition": payload.get("ota_partition"),
            "ota_pending": payload.get("ota_pending"),
            "transport": dict(self._diagnostics[node_id]),
            "heartbeat": heartbeat,
        }


class ServiceAgent:
    def __init__(
        self,
        *,
        keys: dict[str, NodeKey],
        runtime_dir: Path,
        state_dir: Path,
        bind_address: str,
        port: int,
        socket_path: Path,
        stale_after_seconds: float,
        network_probe_interval_seconds: float = 5.0,
        network_probe: Callable[[], ServiceNetworkState] | None = None,
    ) -> None:
        if network_probe_interval_seconds <= 0:
            raise ValueError("network probe interval must be positive")
        self._runtime_dir = runtime_dir
        self._bind_address = bind_address
        self._port = port
        self._socket_path = socket_path
        self._receiver = HeartbeatReceiver(
            keys=keys,
            runtime_dir=runtime_dir,
            state_dir=state_dir,
            stale_after_seconds=stale_after_seconds,
        )
        self._state = ServiceAgentState(keys, state_dir=state_dir)
        self._network_probe_interval_seconds = network_probe_interval_seconds
        self._network_probe = network_probe or (
            lambda: probe_service_network(bind_address=bind_address)
        )
        self._last_network_probe_monotonic = 0.0
        self._network_state: ServiceNetworkState | None = None
        self._started_unix_ms = int(time.time() * 1000)

    def process_datagram(self, datagram: bytes, source_ip: str) -> dict[str, Any]:
        persisted = self._receiver.process_datagram(datagram, source_ip)
        self._state.record(persisted)
        return persisted

    def expire_stale_nodes(self) -> list[str]:
        expired = self._receiver.expire_stale_nodes()
        self._state.mark_offline(expired)
        return expired

    def snapshot(self) -> dict[str, Any]:
        self._refresh_network_state()
        assert self._network_state is not None
        nodes = self._state.nodes()
        return {
            "agent": {
                "ready": True,
                "started_unix_ms": self._started_unix_ms,
                "udp_bind": f"{self._bind_address}:{self._port}",
                "socket": str(self._socket_path),
                "registered_nodes": len(nodes),
                "online_nodes": sum(1 for node in nodes if node["online"]),
            },
            "network": self._network_state.to_dict(),
            "nodes": nodes,
        }

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        snapshot = self.snapshot()
        if command == "status":
            return {"ok": True, **snapshot}
        if command == "nodes":
            return {"ok": True, "nodes": snapshot["nodes"]}
        if command == "network":
            return {"ok": True, "network": snapshot["network"]}
        return {"ok": False, "error": f"unknown command: {command!r}"}

    def _refresh_network_state(self) -> None:
        now = time.monotonic()
        if (
            self._network_state is not None
            and now - self._last_network_probe_monotonic
            < self._network_probe_interval_seconds
        ):
            return
        self._network_state = self._network_probe()
        self._last_network_probe_monotonic = now

    def run(self) -> None:
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.unlink(missing_ok=True)

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind((self._bind_address, self._port))
        udp_socket.setblocking(False)

        api_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        api_socket.bind(str(self._socket_path))
        os.chmod(self._socket_path, 0o660)
        api_socket.listen(8)
        api_socket.setblocking(False)

        selector = selectors.DefaultSelector()
        selector.register(udp_socket, selectors.EVENT_READ, "udp")
        selector.register(api_socket, selectors.EVENT_READ, "api")
        LOGGER.info(
            "CM5 service agent listening on UDP %s:%d and %s",
            self._bind_address,
            self._port,
            self._socket_path,
        )

        try:
            while True:
                for key, _ in selector.select(timeout=1.0):
                    if key.data == "udp":
                        datagram, address = udp_socket.recvfrom(MAX_DATAGRAM_BYTES + 1)
                        try:
                            self.process_datagram(datagram, address[0])
                        except HeartbeatError as exc:
                            LOGGER.warning("rejected heartbeat from %s: %s", address[0], exc)
                    elif key.data == "api":
                        client, _ = api_socket.accept()
                        self._serve_client(client)
                self.expire_stale_nodes()
        finally:
            selector.close()
            udp_socket.close()
            api_socket.close()
            self._socket_path.unlink(missing_ok=True)

    def _serve_client(self, client: socket.socket) -> None:
        with client:
            client.settimeout(1.0)
            request_bytes = b""
            try:
                while not request_bytes.endswith(b"\n"):
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    request_bytes += chunk
                    if len(request_bytes) > MAX_REQUEST_BYTES:
                        raise ValueError("request is too large")
                request = json.loads(request_bytes.decode("utf-8"))
                if not isinstance(request, dict):
                    raise ValueError("request must be a JSON object")
                response = self.handle_request(request)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                response = {"ok": False, "error": str(exc)}
            try:
                client.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
            except OSError:
                LOGGER.debug("service API client disconnected before response")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CM5 service-plane agent")
    parser.add_argument("--bind", default=DEFAULT_BIND_ADDRESS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--keys", type=Path, default=DEFAULT_KEYS_PATH)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET_PATH)
    parser.add_argument("--stale-after", type=float, default=35.0)
    parser.add_argument("--network-probe-interval", type=float, default=5.0)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        agent = ServiceAgent(
            keys=load_node_keys(args.keys),
            runtime_dir=args.runtime_dir,
            state_dir=args.state_dir,
            bind_address=args.bind,
            port=args.port,
            socket_path=args.socket,
            stale_after_seconds=args.stale_after,
            network_probe_interval_seconds=args.network_probe_interval,
        )
        agent.run()
    except KeyboardInterrupt:
        return 130
    except (OSError, HeartbeatError, ValueError) as exc:
        LOGGER.error("service agent stopped: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
