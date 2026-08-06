from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from ventilation_core.service_heartbeat import NodeKey

LOGGER = logging.getLogger("wvc.service_ota")
OTA_PROTOCOL = "WVC-OTA1"
OTA_PORT = 45552
OTA_CHALLENGE_PATH = "/v1/ota/challenge"
OTA_IMAGE_PATH = "/v1/ota/image"
OTA_STATUS_PATH = "/v1/ota/status"
DEFAULT_LEASES_PATH = Path("/var/lib/misc/dnsmasq-wvc.leases")
MAX_IMAGE_BYTES = 0x1D0000
TERMINAL_STATES = frozenset({"succeeded", "failed", "rolled_back", "uncertain"})
BOOT_ID_RE = re.compile(r"^[0-9a-f]{16}$")
NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


class ServiceOtaError(RuntimeError):
    """Raised when a manual service OTA operation cannot complete safely."""


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


def canonical_authorization_message(
    *,
    node_id: str,
    boot_id: str,
    nonce: str,
    image_size: int,
    image_sha256: str,
) -> bytes:
    return (
        f"{OTA_PROTOCOL}\n"
        f"{node_id}\n"
        f"{boot_id}\n"
        f"{nonce}\n"
        f"{image_size}\n"
        f"{image_sha256}\n"
    ).encode("ascii")


def calculate_authorization(
    key: bytes,
    *,
    node_id: str,
    boot_id: str,
    nonce: str,
    image_size: int,
    image_sha256: str,
) -> str:
    message = canonical_authorization_message(
        node_id=node_id,
        boot_id=boot_id,
        nonce=nonce,
        image_size=image_size,
        image_sha256=image_sha256,
    )
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def validate_image(path: Path) -> tuple[int, str]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise ServiceOtaError(f"cannot read OTA image: {exc}") from exc
    if not path.is_file():
        raise ServiceOtaError("OTA image path is not a regular file")
    if stat.st_size <= 0 or stat.st_size > MAX_IMAGE_BYTES:
        raise ServiceOtaError(
            f"OTA image size {stat.st_size} is outside 1..{MAX_IMAGE_BYTES} bytes"
        )

    digest = hashlib.sha256()
    first_byte = b""
    try:
        with path.open("rb") as handle:
            first_byte = handle.read(1)
            digest.update(first_byte)
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ServiceOtaError(f"cannot hash OTA image: {exc}") from exc
    if first_byte != b"\xE9":
        raise ServiceOtaError("OTA image does not start with the ESP application magic byte 0xE9")
    return stat.st_size, digest.hexdigest()


def _validate_service_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ServiceOtaError(f"invalid node service address: {value!r}") from exc
    if address not in ipaddress.ip_network("10.55.0.0/24") or str(address) == "10.55.0.1":
        raise ServiceOtaError(f"node address {value} is outside the private node range")
    return str(address)


def resolve_node_address(
    *,
    node_id: str,
    nodes: Iterable[dict[str, Any]],
    node_key: NodeKey,
    leases_path: Path = DEFAULT_LEASES_PATH,
) -> str:
    for node in nodes:
        if node.get("node_id") != node_id:
            continue
        source_ip = node.get("source_ip")
        if isinstance(source_ip, str) and source_ip:
            return _validate_service_address(source_ip)

    if node_key.mac is None:
        raise ServiceOtaError(
            f"node {node_id} is offline and has no pinned MAC for DHCP lease lookup"
        )
    try:
        lease_lines = leases_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ServiceOtaError(
            f"node {node_id} is offline and DHCP leases cannot be read: {exc}"
        ) from exc

    expected_mac = node_key.mac.lower()
    for line in lease_lines:
        fields = line.split()
        if len(fields) < 3 or fields[1].lower() != expected_mac:
            continue
        return _validate_service_address(fields[2])
    raise ServiceOtaError(f"no current service address is known for node {node_id}")


@dataclass(frozen=True)
class OtaChallenge:
    node_id: str
    boot_id: str
    nonce: str


class OtaHttpClient:
    def __init__(
        self,
        *,
        port: int = OTA_PORT,
        connect_timeout_seconds: float = 5.0,
        transfer_timeout_seconds: float = 20.0,
        connection_factory: Callable[..., http.client.HTTPConnection] = http.client.HTTPConnection,
    ) -> None:
        self._port = port
        self._connect_timeout_seconds = connect_timeout_seconds
        self._transfer_timeout_seconds = transfer_timeout_seconds
        self._connection_factory = connection_factory

    @staticmethod
    def _decode_response(response: http.client.HTTPResponse) -> dict[str, Any]:
        body = response.read()
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceOtaError(
                f"node returned invalid JSON (HTTP {response.status})"
            ) from exc
        if not isinstance(decoded, dict):
            raise ServiceOtaError("node returned a non-object JSON response")
        if response.status < 200 or response.status >= 300 or decoded.get("ok") is not True:
            error = decoded.get("error")
            raise ServiceOtaError(
                f"node rejected OTA request (HTTP {response.status}): {error or decoded}"
            )
        return decoded

    def _get_json(self, address: str, path: str) -> dict[str, Any]:
        connection = self._connection_factory(
            address, self._port, timeout=self._connect_timeout_seconds
        )
        try:
            connection.request("GET", path, headers={"Connection": "close"})
            return self._decode_response(connection.getresponse())
        except (OSError, http.client.HTTPException) as exc:
            raise ServiceOtaError(f"cannot reach OTA endpoint at {address}:{self._port}: {exc}") from exc
        finally:
            connection.close()

    def challenge(self, address: str, expected_node_id: str) -> OtaChallenge:
        response = self._get_json(address, OTA_CHALLENGE_PATH)
        node_id = response.get("node_id")
        boot_id = response.get("boot_id")
        nonce = response.get("nonce")
        if node_id != expected_node_id:
            raise ServiceOtaError(
                f"OTA endpoint identity mismatch: expected {expected_node_id}, got {node_id!r}"
            )
        if not isinstance(boot_id, str) or not BOOT_ID_RE.fullmatch(boot_id):
            raise ServiceOtaError("OTA challenge contains an invalid boot_id")
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise ServiceOtaError("OTA challenge contains an invalid nonce")
        return OtaChallenge(node_id=node_id, boot_id=boot_id, nonce=nonce)

    def status(self, address: str) -> dict[str, Any]:
        return self._get_json(address, OTA_STATUS_PATH)

    def install(
        self,
        *,
        address: str,
        node_key: NodeKey,
        image_path: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        image_size, image_sha256 = validate_image(image_path)
        challenge = self.challenge(address, node_key.node_id)
        authorization = calculate_authorization(
            node_key.hmac_key,
            node_id=node_key.node_id,
            boot_id=challenge.boot_id,
            nonce=challenge.nonce,
            image_size=image_size,
            image_sha256=image_sha256,
        )

        connection = self._connection_factory(
            address, self._port, timeout=self._transfer_timeout_seconds
        )
        bytes_sent = 0
        try:
            connection.putrequest(
                "POST",
                OTA_IMAGE_PATH,
                skip_host=True,
                skip_accept_encoding=True,
            )
            connection.putheader("Host", address)
            connection.putheader("Connection", "close")
            connection.putheader("Content-Type", "application/octet-stream")
            connection.putheader("Content-Length", str(image_size))
            connection.putheader("X-WVC-Node-ID", node_key.node_id)
            connection.putheader("X-WVC-Boot-ID", challenge.boot_id)
            connection.putheader("X-WVC-Nonce", challenge.nonce)
            connection.putheader("X-WVC-Image-Size", str(image_size))
            connection.putheader("X-WVC-Image-SHA256", image_sha256)
            connection.putheader("X-WVC-Authorization", authorization)
            connection.endheaders()

            with image_path.open("rb") as handle:
                while chunk := handle.read(16 * 1024):
                    connection.send(chunk)
                    bytes_sent += len(chunk)
                    if progress is not None:
                        progress(bytes_sent, image_size)
            return self._decode_response(connection.getresponse())
        except (OSError, http.client.HTTPException) as exc:
            if bytes_sent >= image_size:
                raise ServiceOtaError(
                    "OTA image body was sent completely but the final response was lost; "
                    "operation state is uncertain and must be verified with ota-status"
                ) from exc
            raise ServiceOtaError(
                f"OTA transfer failed after {bytes_sent}/{image_size} bytes: {exc}"
            ) from exc
        finally:
            connection.close()


class OtaCoordinator:
    def __init__(
        self,
        *,
        keys: dict[str, NodeKey],
        state_dir: Path,
        leases_path: Path = DEFAULT_LEASES_PATH,
        client: OtaHttpClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._keys = keys
        self._state_dir = state_dir / "ota"
        self._leases_path = leases_path
        self._client = client or OtaHttpClient()
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._operations: dict[str, dict[str, Any]] = {}
        self._threads: dict[str, threading.Thread] = {}

    def _path(self, node_id: str) -> Path:
        return self._state_dir / f"{node_id}.json"

    def _persist(self, node_id: str) -> None:
        _atomic_write_json(self._path(node_id), self._operations[node_id])

    def _set(self, node_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            operation = dict(self._operations[node_id])
            operation.update(updates)
            operation["updated_unix_ms"] = int(time.time() * 1000)
            self._operations[node_id] = operation
            self._persist(node_id)
            return dict(operation)

    def _load_last(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            if node_id in self._operations:
                return dict(self._operations[node_id])
        try:
            value = json.loads(self._path(node_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def start_install(
        self,
        *,
        node_id: str,
        image_path: Path,
        nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        node_key = self._keys.get(node_id)
        if node_key is None:
            raise ServiceOtaError(f"unknown node_id: {node_id}")
        image_path = image_path.expanduser().resolve(strict=False)
        image_size, image_sha256 = validate_image(image_path)
        address = resolve_node_address(
            node_id=node_id,
            nodes=nodes,
            node_key=node_key,
            leases_path=self._leases_path,
        )

        with self._lock:
            existing = self._operations.get(node_id)
            if existing is not None and existing.get("state") not in TERMINAL_STATES:
                raise ServiceOtaError(f"OTA operation for {node_id} is already active")
            if any(
                operation.get("state") not in TERMINAL_STATES
                for other_node, operation in self._operations.items()
                if other_node != node_id
            ):
                raise ServiceOtaError("another node OTA operation is already active")

            operation_id = f"{int(time.time())}-{os.urandom(4).hex()}"
            operation = {
                "operation_id": operation_id,
                "node_id": node_id,
                "address": address,
                "image_path": str(image_path),
                "image_size": image_size,
                "image_sha256": image_sha256,
                "bytes_sent": 0,
                "state": "queued",
                "result": None,
                "error": None,
                "remote": None,
                "started_unix_ms": int(time.time() * 1000),
                "updated_unix_ms": int(time.time() * 1000),
            }
            self._operations[node_id] = operation
            self._persist(node_id)

            thread = threading.Thread(
                target=self._run_install,
                name=f"wvc-ota-{node_id}",
                args=(node_key, image_path, address, operation_id),
                daemon=True,
            )
            self._threads[node_id] = thread
            thread.start()
            return dict(operation)

    def _run_install(
        self,
        node_key: NodeKey,
        image_path: Path,
        address: str,
        operation_id: str,
    ) -> None:
        node_id = node_key.node_id

        def progress(written: int, expected: int) -> None:
            current = self._load_last(node_id)
            if current is None or current.get("operation_id") != operation_id:
                return
            self._set(node_id, state="uploading", bytes_sent=written, image_size=expected)

        try:
            self._set(node_id, state="authorizing")
            accepted = self._client.install(
                address=address,
                node_key=node_key,
                image_path=image_path,
                progress=progress,
            )
            target_partition = accepted.get("target_partition")
            self._set(
                node_id,
                state="rebooting",
                bytes_sent=int(accepted.get("bytes_written", 0)),
                result=accepted,
            )

            deadline = self._monotonic() + 120.0
            saw_pending = False
            while self._monotonic() < deadline:
                self._sleep(2.0)
                try:
                    remote = self._client.status(address)
                except ServiceOtaError:
                    continue
                self._set(node_id, state="validating", remote=remote)
                remote_node_id = remote.get("node_id")
                if remote_node_id != node_id:
                    raise ServiceOtaError(
                        f"post-reboot OTA endpoint identity mismatch: "
                        f"expected {node_id}, got {remote_node_id!r}"
                    )
                partition = remote.get("partition")
                pending = remote.get("pending")
                if partition == target_partition and pending is True:
                    saw_pending = True
                    continue
                if partition == target_partition and pending is False:
                    self._set(node_id, state="succeeded", remote=remote, error=None)
                    return
                if pending is False and partition != target_partition and saw_pending:
                    self._set(
                        node_id,
                        state="rolled_back",
                        remote=remote,
                        error="new image did not pass health validation and the node rolled back",
                    )
                    return

            self._set(
                node_id,
                state="uncertain",
                error="OTA image was accepted but post-reboot validation did not finish within 120 seconds",
            )
        except ServiceOtaError as exc:
            state = "uncertain" if "uncertain" in str(exc).lower() else "failed"
            self._set(node_id, state=state, error=str(exc))
        except Exception as exc:
            LOGGER.exception("unexpected OTA worker failure for node=%s", node_id)
            self._set(node_id, state="failed", error=f"unexpected OTA worker failure: {exc}")

    def status(
        self,
        *,
        node_id: str,
        nodes: list[dict[str, Any]],
        include_remote: bool = True,
    ) -> dict[str, Any]:
        node_key = self._keys.get(node_id)
        if node_key is None:
            raise ServiceOtaError(f"unknown node_id: {node_id}")
        operation = self._load_last(node_id)
        result: dict[str, Any] = {"node_id": node_id, "operation": operation}
        if not include_remote:
            return result

        try:
            address = resolve_node_address(
                node_id=node_id,
                nodes=nodes,
                node_key=node_key,
                leases_path=self._leases_path,
            )
            result["address"] = address
            result["remote"] = self._client.status(address)
        except ServiceOtaError as exc:
            result["remote"] = None
            result["remote_error"] = str(exc)
        return result
