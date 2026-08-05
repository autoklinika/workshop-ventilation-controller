import json
import tempfile
import unittest
from pathlib import Path

from ventilation_core.service_heartbeat import (
    HeartbeatError,
    HeartbeatReceiver,
    NodeKey,
    decode_and_authenticate_frame,
    encode_frame,
    load_node_keys,
)


KEY = bytes(range(32))
NODE_KEY = NodeKey(
    node_id="sensor-zone-1",
    key_id="sensor-zone-1-v1",
    hmac_key=KEY,
    mac="AA:BB:CC:DD:EE:01",
)


def payload(*, seq: int = 1, boot_id: str = "0123456789abcdef") -> dict:
    return {
        "protocol": "WVC-HB1",
        "schema": 1,
        "node_id": "sensor-zone-1",
        "key_id": "sensor-zone-1-v1",
        "mac": "AA:BB:CC:DD:EE:01",
        "boot_id": boot_id,
        "seq": seq,
        "firmware": "0.4.0-stage1",
        "uptime_s": 123,
        "reset_reason": 1,
        "ota_partition": "ota_0",
        "ota_pending": False,
        "wifi_rssi_dbm": -58,
        "sensor_state": "running",
        "measurement_age_ms": 120,
        "sensor_last_error": 0,
        "sensor_detection_failures": 0,
        "sensor_communication_failures": 0,
        "sensor_crc_failures": 0,
        "sensor_successful_measurements": 100,
        "rs485_ready": True,
        "modbus_slave": 1,
        "modbus_monitor_ready": True,
        "modbus_requests_total": 44,
        "modbus_requests_last_60s": 10,
        "last_modbus_request_age_ms": 250,
        "modbus_service_errors": 0,
    }


class ServiceHeartbeatTest(unittest.TestCase):
    def test_key_registry_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keys.json"
            path.write_text(
                json.dumps(
                    {
                        "nodes": {
                            "sensor-zone-1": {
                                "key_id": "sensor-zone-1-v1",
                                "hmac_key_hex": KEY.hex(),
                                "mac": "aa:bb:cc:dd:ee:01",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            keys = load_node_keys(path)
            self.assertEqual(keys["sensor-zone-1"].mac, "AA:BB:CC:DD:EE:01")

    def test_valid_frame_authenticates(self) -> None:
        decoded = decode_and_authenticate_frame(
            encode_frame(payload(), KEY),
            source_ip="10.55.0.101",
            keys={NODE_KEY.node_id: NODE_KEY},
        )
        self.assertEqual(decoded["seq"], 1)

    def test_modified_payload_fails_hmac(self) -> None:
        frame = bytearray(encode_frame(payload(), KEY))
        frame[10] ^= 1
        with self.assertRaises(HeartbeatError):
            decode_and_authenticate_frame(
                bytes(frame),
                source_ip="10.55.0.101",
                keys={NODE_KEY.node_id: NODE_KEY},
            )

    def test_wrong_source_subnet_is_rejected(self) -> None:
        with self.assertRaisesRegex(HeartbeatError, "outside"):
            decode_and_authenticate_frame(
                encode_frame(payload(), KEY),
                source_ip="192.168.1.25",
                keys={NODE_KEY.node_id: NODE_KEY},
            )

    def test_mac_pinning_is_enforced(self) -> None:
        value = payload()
        value["mac"] = "AA:BB:CC:DD:EE:02"
        with self.assertRaisesRegex(HeartbeatError, "MAC does not match"):
            decode_and_authenticate_frame(
                encode_frame(value, KEY),
                source_ip="10.55.0.101",
                keys={NODE_KEY.node_id: NODE_KEY},
            )

    def test_replay_and_closed_boot_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = [100.0]
            receiver = HeartbeatReceiver(
                keys={NODE_KEY.node_id: NODE_KEY},
                runtime_dir=root / "run",
                state_dir=root / "state",
                monotonic=lambda: now[0],
            )
            receiver.process_datagram(encode_frame(payload(seq=1), KEY), "10.55.0.101")
            with self.assertRaisesRegex(HeartbeatError, "replayed"):
                receiver.process_datagram(encode_frame(payload(seq=1), KEY), "10.55.0.101")

            receiver.process_datagram(
                encode_frame(payload(seq=1, boot_id="fedcba9876543210"), KEY),
                "10.55.0.101",
            )
            with self.assertRaisesRegex(HeartbeatError, "previously closed"):
                receiver.process_datagram(encode_frame(payload(seq=2), KEY), "10.55.0.101")

    def test_node_transitions_offline_without_touching_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = [100.0]
            receiver = HeartbeatReceiver(
                keys={NODE_KEY.node_id: NODE_KEY},
                runtime_dir=root / "run",
                state_dir=root / "state",
                stale_after_seconds=35.0,
                monotonic=lambda: now[0],
            )
            receiver.process_datagram(encode_frame(payload(), KEY), "10.55.0.101")
            now[0] = 136.0
            self.assertEqual(receiver.expire_stale_nodes(), ["sensor-zone-1"])
            stored = json.loads(
                (root / "run" / "nodes" / "sensor-zone-1.json").read_text(encoding="utf-8")
            )
            self.assertFalse(stored["online"])
            self.assertEqual(stored["heartbeat"]["modbus_requests_total"], 44)


if __name__ == "__main__":
    unittest.main()
