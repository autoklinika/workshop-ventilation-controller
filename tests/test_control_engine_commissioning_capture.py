import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_TOOL = ROOT / "tools" / "control_engine_commissioning_capture.py"
VALIDATOR_TOOL = ROOT / "tools" / "control_engine_validate_commissioning_dataset.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load_module("commissioning_capture", CAPTURE_TOOL)
validator = load_module("commissioning_dataset_validator", VALIDATOR_TOOL)


def state(*, aq: str = "NORMAL", phase: str = "ACTIVE", supply_v: float = 1.0, extract_v: float = 1.0):
    return {
        "mode": "MANUAL",
        "setpoints": {"supply_voltage": supply_v, "extract_voltage": extract_v},
        "hardware_ready": True,
        "output_state_known": True,
        "tacho": {
            "ready": True,
            "worker_alive": True,
            "supply": {"rpm": 405.0, "valid": True},
            "extract": {"rpm": 412.0, "valid": True},
        },
        "shadow_automation": {
            "actuation_supported": False,
            "status": "READY",
            "zones": [
                {
                    "zone": "zone-1",
                    "sensor_usable": True,
                    "outside_temperature_usable": True,
                    "air_quality_level": aq,
                    "calendar_phase": phase,
                    "inside_temperature_celsius": 21.5,
                    "outside_temperature_celsius": 5.0,
                }
            ],
        },
    }


class CommissioningCaptureTests(unittest.TestCase):
    def test_capture_requests_status_only_and_writes_workshop_jsonl(self) -> None:
        requests = []
        statuses = [
            {"ok": True, "state": state(aq="NORMAL", phase="ACTIVE")},
            {"ok": True, "state": state(aq="BOOST", phase="INACTIVE")},
        ]
        current = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        clock_values = iter(
            [
                current,
                current + timedelta(seconds=1),
                current + timedelta(seconds=2),
            ]
        )

        def requester(socket_path, request):
            requests.append((socket_path, request))
            return statuses[len(requests) - 1]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "session.jsonl"
            result = capture.capture_session(
                socket_path=Path("/tmp/fake.sock"),
                output=output,
                session_id="workshop-test",
                samples=2,
                interval_seconds=1.0,
                requester=requester,
                clock=lambda: next(clock_values),
                sleeper=lambda _: None,
            )
            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([request for _, request in requests], [{"command": "status"}, {"command": "status"}])
        self.assertEqual(records[0]["environment"], "WORKSHOP")
        self.assertFalse(records[0]["actuation_authority_granted"])
        self.assertFalse(records[0]["core_writes_performed"])
        self.assertEqual(result["captured_samples"], 2)

    def test_offline_validator_accepts_representative_two_state_fixture(self) -> None:
        header = {
            "record_type": "session",
            "schema_version": 1,
            "session_id": "dataset-test",
            "environment": "WORKSHOP",
            "source": "ventilation-core:status",
            "started_at_utc": "2026-08-28T12:00:00+00:00",
            "requested_samples": 2,
            "interval_seconds": 1.0,
            "actuation_authority_granted": False,
            "core_writes_performed": False,
        }
        samples = [
            {
                "record_type": "sample",
                "schema_version": 1,
                "session_id": "dataset-test",
                "sequence": 0,
                "captured_at_utc": "2026-08-28T12:00:01+00:00",
                "state": state(aq="NORMAL", phase="ACTIVE"),
            },
            {
                "record_type": "sample",
                "schema_version": 1,
                "session_id": "dataset-test",
                "sequence": 1,
                "captured_at_utc": "2026-08-28T12:00:02+00:00",
                "state": state(aq="BOOST", phase="INACTIVE", supply_v=2.0, extract_v=2.0),
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "dataset.jsonl"
            dataset.write_text(
                "\n".join(json.dumps(row) for row in [header, *samples]) + "\n",
                encoding="utf-8",
            )
            result = validator.validate_dataset(dataset)

        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["coverage_warnings"], [])
        self.assertTrue(result["ready_for_manual_commissioning_review"])
        self.assertFalse(result["tuning_recommendation_generated"])
        self.assertFalse(result["actuation_authority_granted"])
        self.assertFalse(result["core_writes_performed"])

    def test_dataset_with_only_zero_setpoints_is_flagged_not_recommended(self) -> None:
        header = {
            "record_type": "session",
            "schema_version": 1,
            "session_id": "zero-only",
            "environment": "WORKSHOP",
            "source": "ventilation-core:status",
            "started_at_utc": "2026-08-28T12:00:00+00:00",
            "requested_samples": 1,
            "interval_seconds": 1.0,
            "actuation_authority_granted": False,
            "core_writes_performed": False,
        }
        sample = {
            "record_type": "sample",
            "schema_version": 1,
            "session_id": "zero-only",
            "sequence": 0,
            "captured_at_utc": "2026-08-28T12:00:01+00:00",
            "state": state(supply_v=0.0, extract_v=0.0),
        }
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "dataset.jsonl"
            dataset.write_text(
                json.dumps(header) + "\n" + json.dumps(sample) + "\n",
                encoding="utf-8",
            )
            result = validator.validate_dataset(dataset)
        self.assertIn("NO_NONZERO_LOCAL_FAN_SETPOINTS", result["coverage_warnings"])
        self.assertFalse(result["ready_for_manual_commissioning_review"])
        self.assertFalse(result["tuning_recommendation_generated"])

    def test_capture_source_has_no_core_write_command(self) -> None:
        text = CAPTURE_TOOL.read_text(encoding="utf-8")
        self.assertIn('{"command": "status"}', text)
        for forbidden in (
            '"command": "set"',
            '"command": "stop"',
            '"command": "shutdown"',
            "control-engine-replace",
            "aero-speed",
            "aero-airing",
            "systemctl",
            "subprocess",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
