from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import selectors
import socket
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("wvc.service_heartbeat")
PROTOCOL = "WVC-HB1"
SCHEMA_VERSION = 1
DEFAULT_PORT = 45551
MAX_DATAGRAM_BYTES = 2048
NODE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
MAC_RE = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$")


class HeartbeatError(ValueError):
    """Raised when a heartbeat frame is invalid or unauthenticated."""


@dataclass(frozen=True)
class NodeKey:
    node_id: str
    key_id: str
    hmac_key: bytes
    mac: str | None = None


@dataclass
class ReplayRecord:
    boot_id: str = ""
    max_seq: int = -1
    previous_boot_ids: list[str] = field(default_factory=list)


@dataclass
class NodeRuntime:
    last_received_monotonic: float = 0.0
    online: bool = False
    last_payload: dict[str, Any] | None = None


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


def load_node_keys(path: Path) -> dict[str, NodeKey]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeartbeatError(f"cannot load key registry: {exc}") from exc

    raw_nodes = document.get("nodes") if isinstance(document, dict) else None
    if not isinstance(raw_nodes, dict) or not raw_nodes:
        raise HeartbeatError("key registry must contain a non-empty 'nodes' object")

    result: dict[str, NodeKey] = {}
    for node_id, raw in raw_nodes.items():
        if not isinstance(node_id, str) or not NODE_ID_RE.fullmatch(node_id):
            raise HeartbeatError(f"invalid node_id in key registry: {node_id!r}")
        if not isinstance(raw, dict):
            raise HeartbeatError(f"registry entry for {node_id} must be an object")

        key_id = raw.get("key_id")
        key_hex = raw.get("hmac_key_hex")
        mac = raw.get("mac")
        if not isinstance(key_id, str) or not KEY_ID_RE.fullmatch(key_id):
            raise HeartbeatError(f"invalid key_id for {node_id}")
        if not isinstance(key_hex, str):
            raise HeartbeatError(f"missing hmac_key_hex for {node_id}")
        try:
            key = bytes.fromhex(key_hex)
        except ValueError as exc:
            raise HeartbeatError(f"invalid hmac_key_hex for {node_id}") from exc
        if len(key) != 32:
            raise HeartbeatError(f"HMAC key for {node_id} must be exactly 32 bytes")

        normalized_mac: str | None = None
        if mac is not None:
            if not isinstance(mac, str):
                raise HeartbeatError(f"invalid MAC for {node_id}")
            normalized_mac = mac.upper()
            if not MAC_RE.fullmatch(normalized_mac):
                raise HeartbeatError(f"invalid MAC for {node_id}")

        result[node_id] = NodeKey(node_id, key_id, key, normalized_mac)
    return result


def encode_frame(payload: dict[str, Any], key: bytes) -> bytes:
    payload_bytes = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    signature = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest().encode("ascii")
    return payload_bytes + b"\n" + signature


def decode_and_authenticate_frame(
    datagram: bytes,
    *,
    source_ip: str,
    keys: dict[str, NodeKey],
) -> dict[str, Any]:
    if not datagram or len(datagram) > MAX_DATAGRAM_BYTES:
        raise HeartbeatError("datagram size is outside the accepted range")

    try:
        payload_bytes, signature_bytes = datagram.rsplit(b"\n", 1)
    except ValueError as exc:
        raise HeartbeatError("frame separator is missing") from exc
    if len(signature_bytes) != 64:
        raise HeartbeatError("signature must be a 64-character SHA-256 hex digest")
    try:
        signature = bytes.fromhex(signature_bytes.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HeartbeatError("signature is not valid hexadecimal") from exc

    try:
        source = ipaddress.ip_address(source_ip)
    except ValueError as exc:
        raise HeartbeatError("source address is invalid") from exc
    if source not in ipaddress.ip_network("10.55.0.0/24"):
        raise HeartbeatError("source address is outside the private service subnet")

    try:
        payload = json.loads(payload_bytes.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HeartbeatError("payload is not valid ASCII JSON") from exc
    if not isinstance(payload, dict):
        raise HeartbeatError("payload must be a JSON object")

    node_id = payload.get("node_id")
    key_id = payload.get("key_id")
    if not isinstance(node_id, str) or not NODE_ID_RE.fullmatch(node_id):
        raise HeartbeatError("invalid node_id")
    node_key = keys.get(node_id)
    if node_key is None:
        raise HeartbeatError("unknown node_id")
    if key_id != node_key.key_id:
        raise HeartbeatError("key_id does not match the registered node")

    expected = hmac.new(node_key.hmac_key, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise HeartbeatError("HMAC authentication failed")

    _validate_payload(payload, node_key)
    return payload


def _require_int(payload: dict[str, Any], name: str, *, minimum: int, maximum: int) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HeartbeatError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise HeartbeatError(f"{name} is outside the accepted range")
    return value


def _validate_payload(payload: dict[str, Any], node_key: NodeKey) -> None:
    if payload.get("protocol") != PROTOCOL:
        raise HeartbeatError("unsupported protocol")
    if payload.get("schema") != SCHEMA_VERSION:
        raise HeartbeatError("unsupported schema version")

    mac = payload.get("mac")
    if not isinstance(mac, str) or not MAC_RE.fullmatch(mac.upper()):
        raise HeartbeatError("invalid MAC")
    if node_key.mac is not None and mac.upper() != node_key.mac:
        raise HeartbeatError("MAC does not match the registered node")

    boot_id = payload.get("boot_id")
    if not isinstance(boot_id, str) or not re.fullmatch(r"[0-9a-f]{16}", boot_id):
        raise HeartbeatError("boot_id must be 16 lowercase hexadecimal characters")

    _require_int(payload, "seq", minimum=0, maximum=(1 << 63) - 1)
    _require_int(payload, "uptime_s", minimum=0, maximum=(1 << 32) - 1)
    _require_int(payload, "wifi_rssi_dbm", minimum=-127, maximum=0)
    _require_int(payload, "measurement_age_ms", minimum=-1, maximum=(1 << 31) - 1)
    _require_int(payload, "modbus_requests_total", minimum=0, maximum=(1 << 32) - 1)
    _require_int(payload, "modbus_requests_last_60s", minimum=0, maximum=(1 << 32) - 1)
    _require_int(payload, "last_modbus_request_age_ms", minimum=-1, maximum=(1 << 31) - 1)

    for name in ("firmware", "sensor_state", "ota_partition"):
        value = payload.get(name)
        if not isinstance(value, str) or not value or len(value) > 32:
            raise HeartbeatError(f"{name} must be a non-empty string up to 32 characters")

    for name in ("rs485_ready", "modbus_monitor_ready", "ota_pending"):
        if not isinstance(payload.get(name), bool):
            raise HeartbeatError(f"{name} must be boolean")


class ReplayStore:
    def __init__(self, state_dir: Path, *, history_limit: int = 8) -> None:
        self._state_dir = state_dir
        self._history_limit = history_limit
        self._records: dict[str, ReplayRecord] = {}

    def _path(self, node_id: str) -> Path:
        return self._state_dir / f"{node_id}.json"

    def _load(self, node_id: str) -> ReplayRecord:
        if node_id in self._records:
            return self._records[node_id]
        path = self._path(node_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            record = ReplayRecord(
                boot_id=str(raw.get("boot_id", "")),
                max_seq=int(raw.get("max_seq", -1)),
                previous_boot_ids=[str(value) for value in raw.get("previous_boot_ids", [])],
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            record = ReplayRecord()
        self._records[node_id] = record
        return record

    def accept(self, payload: dict[str, Any]) -> None:
        node_id = payload["node_id"]
        boot_id = payload["boot_id"]
        seq = payload["seq"]
        record = self._load(node_id)

        if boot_id == record.boot_id:
            if seq <= record.max_seq:
                raise HeartbeatError("replayed or reordered sequence")
            record.max_seq = seq
        else:
            if boot_id in record.previous_boot_ids:
                raise HeartbeatError("heartbeat belongs to a previously closed boot session")
            if record.boot_id:
                record.previous_boot_ids.append(record.boot_id)
                record.previous_boot_ids = record.previous_boot_ids[-self._history_limit :]
            record.boot_id = boot_id
            record.max_seq = seq

        _atomic_write_json(
            self._path(node_id),
            {
                "boot_id": record.boot_id,
                "max_seq": record.max_seq,
                "previous_boot_ids": record.previous_boot_ids,
            },
        )


class HeartbeatReceiver:
    def __init__(
        self,
        *,
        keys: dict[str, NodeKey],
        runtime_dir: Path,
        state_dir: Path,
        stale_after_seconds: float = 35.0,
        monotonic=time.monotonic,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self._keys = keys
        self._runtime_dir = runtime_dir
        self._replay = ReplayStore(state_dir)
        self._stale_after_seconds = stale_after_seconds
        self._monotonic = monotonic
        self._runtime: dict[str, NodeRuntime] = {
            node_id: NodeRuntime() for node_id in keys
        }

    def process_datagram(self, datagram: bytes, source_ip: str) -> dict[str, Any]:
        payload = decode_and_authenticate_frame(datagram, source_ip=source_ip, keys=self._keys)
        self._replay.accept(payload)

        node_id = payload["node_id"]
        now_monotonic = self._monotonic()
        runtime = self._runtime[node_id]
        transition_online = not runtime.online
        runtime.last_received_monotonic = now_monotonic
        runtime.online = True
        runtime.last_payload = payload

        persisted = {
            "online": True,
            "received_unix_ms": int(time.time() * 1000),
            "source_ip": source_ip,
            "heartbeat": payload,
        }
        _atomic_write_json(self._runtime_dir / "nodes" / f"{node_id}.json", persisted, mode=0o640)
        if transition_online:
            LOGGER.info("node=%s service heartbeat online", node_id)
        return persisted

    def expire_stale_nodes(self) -> list[str]:
        now = self._monotonic()
        expired: list[str] = []
        for node_id, runtime in self._runtime.items():
            if not runtime.online:
                continue
            if now - runtime.last_received_monotonic <= self._stale_after_seconds:
                continue
            runtime.online = False
            expired.append(node_id)
            persisted = {
                "online": False,
                "received_unix_ms": int(time.time() * 1000),
                "heartbeat": runtime.last_payload,
            }
            _atomic_write_json(self._runtime_dir / "nodes" / f"{node_id}.json", persisted, mode=0o640)
            LOGGER.warning("node=%s service heartbeat offline", node_id)
        return expired


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Receive authenticated KAmod service heartbeats")
    parser.add_argument("--bind", default="10.55.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--keys", type=Path, default=Path("/etc/wvc-service-heartbeat/keys.json"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("/run/wvc-service-heartbeat"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/wvc-service-heartbeat"))
    parser.add_argument("--stale-after", type=float, default=35.0)
    parser.add_argument("--log-level", default="INFO")
    return parser


def run(args: argparse.Namespace) -> None:
    keys = load_node_keys(args.keys)
    receiver = HeartbeatReceiver(
        keys=keys,
        runtime_dir=args.runtime_dir,
        state_dir=args.state_dir,
        stale_after_seconds=args.stale_after,
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    sock.setblocking(False)

    selector = selectors.DefaultSelector()
    selector.register(sock, selectors.EVENT_READ)
    LOGGER.info("listening for authenticated service heartbeats on %s:%d", args.bind, args.port)

    while True:
        for key, _ in selector.select(timeout=1.0):
            if key.fileobj is not sock:
                continue
            datagram, address = sock.recvfrom(MAX_DATAGRAM_BYTES + 1)
            source_ip = address[0]
            try:
                receiver.process_datagram(datagram, source_ip)
            except HeartbeatError as exc:
                LOGGER.warning("rejected heartbeat from %s: %s", source_ip, exc)
        receiver.expire_stale_nodes()


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        run(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, HeartbeatError, ValueError) as exc:
        LOGGER.error("service heartbeat receiver failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
