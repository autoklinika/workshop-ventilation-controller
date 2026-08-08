from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from ventilation_core.service_heartbeat import NodeKey
from ventilation_core.service_ota import (
    OtaCoordinator,
    OtaHttpClient,
    ServiceOtaError,
    ServiceOtaUncertainError,
    calculate_authorization,
    canonical_authorization_message,
    resolve_node_address,
    validate_image,
)


class FakeClient:
    def __init__(self) -> None:
        self.install_calls = 0
        self.status_calls = 0
        self.installed = False

    def install(self, *, address, node_key, image_path, progress=None):
        self.install_calls += 1
        size = image_path.stat().st_size
        if progress:
            progress(size, size)
        self.installed = True
        return {
            "ok": True,
            "result": "accepted",
            "bytes_written": size,
            "target_partition": "ota_1",
        }

    def status(self, address):
        self.status_calls += 1
        return {
            "ok": True,
            "node_id": "sensor-node-1",
            "partition": "ota_1" if self.installed else "ota_0",
            "pending": False,
            "state": "idle",
        }


class UncertainClient(FakeClient):
    def install(self, *, address, node_key, image_path, progress=None):
        self.install_calls += 1
        size = image_path.stat().st_size
        if progress:
            progress(size, size)
        raise ServiceOtaUncertainError("complete body sent; response lost")


class JsonResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body


class ServiceOtaTests(unittest.TestCase):
    def test_canonical_authorization_and_hmac_are_stable(self) -> None:
        message = canonical_authorization_message(
            node_id="sensor-node-1",
            boot_id="0123456789abcdef",
            nonce="00112233445566778899aabbccddeeff",
            image_size=1234,
            image_sha256="a" * 64,
        )
        self.assertEqual(
            message,
            b"WVC-OTA1\nsensor-node-1\n0123456789abcdef\n"
            b"00112233445566778899aabbccddeeff\n1234\n" + b"a" * 64 + b"\n",
        )
        key = bytes(range(32))
        self.assertEqual(
            calculate_authorization(
                key,
                node_id="sensor-node-1",
                boot_id="0123456789abcdef",
                nonce="00112233445566778899aabbccddeeff",
                image_size=1234,
                image_sha256="a" * 64,
            ),
            hmac.new(key, message, hashlib.sha256).hexdigest(),
        )

    def test_image_validation_requires_esp_app_magic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.bin"
            valid.write_bytes(b"\xE9" + b"payload")
            size, digest = validate_image(valid)
            self.assertEqual(size, 8)
            self.assertEqual(digest, hashlib.sha256(valid.read_bytes()).hexdigest())

            invalid = Path(directory) / "invalid.bin"
            invalid.write_bytes(b"not-an-app")
            with self.assertRaises(ServiceOtaError):
                validate_image(invalid)

    def test_offline_node_uses_pinned_mac_dhcp_lease(self) -> None:
        key = NodeKey(
            "sensor-node-2",
            "sensor-node-2-v1",
            b"k" * 32,
            "88:13:BF:01:37:28",
        )
        with tempfile.TemporaryDirectory() as directory:
            leases = Path(directory) / "leases"
            leases.write_text(
                "1786029999 88:13:bf:01:37:28 10.55.0.110 sensor-node-2 *\n",
                encoding="utf-8",
            )
            self.assertEqual(
                resolve_node_address(
                    node_id="sensor-node-2",
                    nodes=[{"node_id": "sensor-node-2", "source_ip": None}],
                    node_key=key,
                    leases_path=leases,
                ),
                "10.55.0.110",
            )

    def test_default_transfer_timeout_allows_slow_flash_commit(self) -> None:
        client = OtaHttpClient()
        self.assertEqual(client._transfer_timeout_seconds, 180.0)
        self.assertEqual(client._request_attempts, 3)
        self.assertEqual(client._retry_delay_seconds, 1.0)

    def test_get_json_retries_transient_transport_failures(self) -> None:
        attempts = 0

        class Connection:
            def request(self, method, path, headers=None):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise TimeoutError("timed out")

            def getresponse(self):
                return JsonResponse(
                    200,
                    {
                        "ok": True,
                        "node_id": "sensor-node-1",
                        "partition": "ota_1",
                        "pending": False,
                        "state": "idle",
                    },
                )

            def close(self):
                pass

        client = OtaHttpClient(
            connection_factory=lambda *args, **kwargs: Connection(),
            retry_delay_seconds=0,
            sleep=lambda _: None,
        )
        result = client.status("10.55.0.106")
        self.assertTrue(result["ok"])
        self.assertEqual(attempts, 3)

    def test_get_json_does_not_retry_rejected_response(self) -> None:
        attempts = 0

        class Connection:
            def request(self, method, path, headers=None):
                nonlocal attempts
                attempts += 1

            def getresponse(self):
                return JsonResponse(
                    401,
                    {"ok": False, "error": "rejected"},
                )

            def close(self):
                pass

        client = OtaHttpClient(
            connection_factory=lambda *args, **kwargs: Connection(),
            retry_delay_seconds=0,
            sleep=lambda _: None,
        )
        with self.assertRaises(ServiceOtaError):
            client.status("10.55.0.106")
        self.assertEqual(attempts, 1)

    def test_coordinator_runs_one_node_and_persists_success(self) -> None:
        key = NodeKey(
            "sensor-node-1",
            "sensor-node-1-v1",
            b"k" * 32,
            "88:13:BF:00:52:D0",
        )
        fake = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "app.bin"
            image.write_bytes(b"\xE9" + b"firmware")
            coordinator = OtaCoordinator(
                keys={key.node_id: key},
                state_dir=root / "state",
                client=fake,
                sleep=lambda _: None,
            )
            operation = coordinator.start_install(
                node_id=key.node_id,
                image_path=image,
                nodes=[{"node_id": key.node_id, "source_ip": "10.55.0.106"}],
            )
            self.assertEqual(operation["state"], "queued")
            thread = coordinator._threads[key.node_id]
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            status = coordinator.status(
                node_id=key.node_id,
                nodes=[{"node_id": key.node_id, "source_ip": "10.55.0.106"}],
                include_remote=False,
            )
            self.assertEqual(status["operation"]["state"], "succeeded")
            self.assertEqual(status["operation"]["source_partition"], "ota_0")
            self.assertEqual(status["operation"]["target_partition"], "ota_1")
            persisted = json.loads(
                (root / "state" / "ota" / f"{key.node_id}.json").read_text()
            )
            self.assertEqual(persisted["state"], "succeeded")
            self.assertEqual(fake.install_calls, 1)

    def test_active_status_does_not_open_second_node_connection(self) -> None:
        key = NodeKey(
            "sensor-node-1",
            "sensor-node-1-v1",
            b"k" * 32,
            "88:13:BF:00:52:D0",
        )
        fake = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            coordinator = OtaCoordinator(
                keys={key.node_id: key},
                state_dir=Path(directory) / "state",
                client=fake,
            )
            coordinator._operations[key.node_id] = {
                "node_id": key.node_id,
                "address": "10.55.0.106",
                "state": "uploading",
                "remote": None,
            }
            status = coordinator.status(
                node_id=key.node_id,
                nodes=[{"node_id": key.node_id, "source_ip": "10.55.0.106"}],
            )
            self.assertTrue(status["remote_deferred"])
            self.assertIsNone(status["remote"])
            self.assertEqual(fake.status_calls, 0)

    def test_complete_send_without_commit_is_reconciled_as_failed(self) -> None:
        key = NodeKey(
            "sensor-node-1",
            "sensor-node-1-v1",
            b"k" * 32,
            "88:13:BF:00:52:D0",
        )
        fake = UncertainClient()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "app.bin"
            image.write_bytes(b"\xE9" + b"firmware")
            coordinator = OtaCoordinator(
                keys={key.node_id: key},
                state_dir=root / "state",
                client=fake,
                sleep=lambda _: None,
            )
            coordinator.start_install(
                node_id=key.node_id,
                image_path=image,
                nodes=[{"node_id": key.node_id, "source_ip": "10.55.0.106"}],
            )
            thread = coordinator._threads[key.node_id]
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            status = coordinator.status(
                node_id=key.node_id,
                nodes=[{"node_id": key.node_id, "source_ip": "10.55.0.106"}],
                include_remote=False,
            )
            self.assertEqual(status["operation"]["state"], "failed")
            self.assertIn("source partition", status["operation"]["error"])


if __name__ == "__main__":
    unittest.main()
