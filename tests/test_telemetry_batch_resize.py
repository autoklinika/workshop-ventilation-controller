from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ventilation_core.telemetry.agent import TelemetryAgent
from ventilation_core.telemetry.http_client import (
    AIBridgeRequestTooLarge,
    AIBridgeTelemetryClient,
)
from ventilation_core.telemetry.store import TelemetryStore


ROOT = Path(__file__).resolve().parents[1]


class FakeStateReader:
    def read_state(self):
        return {
            "mode": "STOP",
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "hardware_ready": True,
            "output_state_known": True,
            "consecutive_hardware_failures": 0,
            "active_alarms": [],
            "sensor_bus": None,
        }


class OversizeOnceSender:
    def __init__(self) -> None:
        self.payload_sizes: list[int] = []
        self.first = True

    def send_batch(self, payload):
        count = len(payload["samples"])
        self.payload_sizes.append(count)
        if self.first:
            self.first = False
            raise AIBridgeRequestTooLarge("AI Bridge HTTP 413: request too large")
        return {
            "schema_version": 1,
            "source_id": payload["source_id"],
            "batch_id": payload["batch_id"],
            "status": "accepted",
            "received": count,
            "stored": count,
            "duplicates": 0,
            "rejected": 0,
            "server_time": "2026-08-18T13:00:00Z",
        }


class TelemetryBatchResizeTest(unittest.TestCase):
    def make_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        store = TelemetryStore(Path(tempdir.name) / "telemetry.sqlite3")
        store.initialize()
        return store

    def test_store_release_preserves_samples_and_allows_smaller_batch(self):
        store = self.make_store()
        for index in range(4):
            store.append_snapshot({"mode": "STOP"}, sample_id=f"sample-{index}")

        first = store.reserve_batch(4)
        assert first is not None
        self.assertEqual(len(first.samples), 4)

        released = store.release_batch(first.batch_id)
        self.assertEqual(released, 4)
        self.assertEqual(store.pending_count(), 4)

        second = store.reserve_batch(2)
        assert second is not None
        self.assertNotEqual(second.batch_id, first.batch_id)
        self.assertEqual(len(second.samples), 2)
        self.assertEqual(store.total_count(), 4)

    def test_agent_halves_oversized_batch_without_losing_samples(self):
        store = self.make_store()
        for index in range(4):
            store.append_snapshot({"mode": "STOP"}, sample_id=f"sample-{index}")

        sender = OversizeOnceSender()
        agent = TelemetryAgent(
            store=store,
            state_reader=FakeStateReader(),
            batch_sender=sender,
            source_id="workshop-ventilation-cm5-01",
            batch_size=4,
        )

        self.assertFalse(agent.sync_once())
        self.assertEqual(agent.batch_size, 2)
        self.assertEqual(store.pending_count(), 4)

        self.assertTrue(agent.sync_once())
        self.assertEqual(store.pending_count(), 2)
        self.assertTrue(agent.sync_once())
        self.assertEqual(store.pending_count(), 0)
        self.assertEqual(sender.payload_sizes, [4, 2, 2])

    def test_single_oversized_sample_stays_reserved_and_pending(self):
        store = self.make_store()
        store.append_snapshot({"mode": "STOP"}, sample_id="single")

        class AlwaysOversize:
            def send_batch(self, payload):
                raise AIBridgeRequestTooLarge("AI Bridge HTTP 413: request too large")

        agent = TelemetryAgent(
            store=store,
            state_reader=FakeStateReader(),
            batch_sender=AlwaysOversize(),
            source_id="workshop-ventilation-cm5-01",
            batch_size=1,
        )

        with self.assertRaises(AIBridgeRequestTooLarge):
            agent.sync_once()
        self.assertEqual(store.pending_count(), 1)
        reserved = store.reserve_batch(1)
        assert reserved is not None
        self.assertEqual(len(reserved.samples), 1)

    def test_http_client_classifies_413(self):
        client = AIBridgeTelemetryClient("http://127.0.0.1:8080")
        http_error = HTTPError(
            url="http://127.0.0.1:8080/api/v1/ventilation/telemetry/batches",
            code=413,
            msg="Content Too Large",
            hdrs=None,
            fp=BytesIO(b'{"error":"request_too_large"}'),
        )
        with patch(
            "ventilation_core.telemetry.http_client.request.urlopen",
            side_effect=http_error,
        ):
            with self.assertRaises(AIBridgeRequestTooLarge):
                client.send_batch({"samples": []})

    def test_http_client_rejects_oversized_body_before_network_send(self):
        client = AIBridgeTelemetryClient(
            "http://127.0.0.1:8080",
            max_body_bytes=128,
        )
        payload = {"samples": [{"metrics": {"blob": "x" * 256}}]}
        with patch("ventilation_core.telemetry.http_client.request.urlopen") as urlopen:
            with self.assertRaisesRegex(
                AIBridgeRequestTooLarge,
                "before send",
            ):
                client.send_batch(payload)
        urlopen.assert_not_called()

    def test_http_client_allows_body_at_or_under_local_limit(self):
        client = AIBridgeTelemetryClient(
            "http://127.0.0.1:8080",
            max_body_bytes=1024,
        )

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok":true}'

        with patch(
            "ventilation_core.telemetry.http_client.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            response = client.send_batch({"samples": []})
        self.assertEqual(response, {"ok": True})
        urlopen.assert_called_once()

    def test_production_systemd_batch_cap_is_50(self):
        unit = (ROOT / "deploy/systemd/wvc-telemetry-sync.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("--batch-size 50", unit)
        self.assertNotIn("--batch-size 100", unit)


if __name__ == "__main__":
    unittest.main()
