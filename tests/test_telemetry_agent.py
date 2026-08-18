from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ventilation_core.telemetry.agent import TelemetryAgent
from ventilation_core.telemetry.store import TelemetryStore


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


class FakeSender:
    def __init__(self) -> None:
        self.payloads = []
        self.duplicate_mode = False

    def send_batch(self, payload):
        self.payloads.append(payload)
        count = len(payload["samples"])
        return {
            "schema_version": 1,
            "source_id": payload["source_id"],
            "batch_id": payload["batch_id"],
            "status": "accepted",
            "received": count,
            "stored": 0 if self.duplicate_mode else count,
            "duplicates": count if self.duplicate_mode else 0,
            "rejected": 0,
            "server_time": "2026-08-10T09:00:00Z",
        }


class FailingSender:
    def send_batch(self, payload):
        raise RuntimeError("network down")


class TelemetryAgentTest(unittest.TestCase):
    def make_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        store = TelemetryStore(Path(tempdir.name) / "telemetry.sqlite3")
        store.initialize()
        return store

    def make_agent(self, store, sender):
        return TelemetryAgent(
            store=store,
            state_reader=FakeStateReader(),
            batch_sender=sender,
            source_id="workshop-ventilation-cm5-01",
            batch_size=100,
        )

    def test_capture_and_sync_builds_contract_payload(self) -> None:
        store = self.make_store()
        sender = FakeSender()
        agent = self.make_agent(store, sender)
        agent.capture_once()
        sent = agent.sync_once()
        self.assertTrue(sent)
        self.assertEqual(store.pending_count(), 0)
        self.assertEqual(len(sender.payloads), 1)
        payload = sender.payloads[0]
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["source_id"], "workshop-ventilation-cm5-01")
        self.assertEqual(len(payload["samples"]), 1)
        self.assertEqual(payload["samples"][0]["sequence"], 1)
        self.assertEqual(payload["samples"][0]["metrics"]["mode"], "STOP")

    def test_capture_only_mode_keeps_local_history_pending(self) -> None:
        store = self.make_store()
        agent = self.make_agent(store, None)

        self.assertFalse(agent.sync_enabled)
        agent.capture_once()
        self.assertEqual(store.total_count(), 1)
        self.assertEqual(store.pending_count(), 1)
        self.assertFalse(agent.sync_once())

        batch = store.reserve_batch(100)
        assert batch is not None
        self.assertEqual(len(batch.samples), 1)
        self.assertEqual(batch.samples[0].sequence, 1)

    def test_failed_sync_keeps_same_batch_for_retry(self) -> None:
        store = self.make_store()
        agent = self.make_agent(store, FailingSender())
        agent.capture_once()
        first_batch = store.reserve_batch(100)
        assert first_batch is not None
        with self.assertRaisesRegex(RuntimeError, "network down"):
            agent.sync_once()
        second_batch = store.reserve_batch(100)
        assert second_batch is not None
        self.assertEqual(store.pending_count(), 1)
        self.assertEqual(first_batch.batch_id, second_batch.batch_id)
        self.assertEqual(first_batch.created_at, second_batch.created_at)

    def test_duplicate_ack_marks_sample_synced(self) -> None:
        store = self.make_store()
        sender = FakeSender()
        sender.duplicate_mode = True
        agent = self.make_agent(store, sender)
        agent.capture_once()
        self.assertTrue(agent.sync_once())
        self.assertEqual(store.pending_count(), 0)

    def test_bad_ack_does_not_mark_pending_as_synced(self) -> None:
        store = self.make_store()

        class BadSender(FakeSender):
            def send_batch(self, payload):
                ack = super().send_batch(payload)
                ack["batch_id"] = "wrong"
                return ack

        agent = self.make_agent(store, BadSender())
        agent.capture_once()
        with self.assertRaisesRegex(RuntimeError, "batch_id mismatch"):
            agent.sync_once()
        self.assertEqual(store.pending_count(), 1)


if __name__ == "__main__":
    unittest.main()
