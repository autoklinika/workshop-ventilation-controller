from __future__ import annotations

import unittest
from pathlib import Path

from ventilation_core.service_heartbeat import (
    NodeKey,
    decode_and_authenticate_frame,
    encode_frame,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = bytes(range(32))
NODE_KEY = NodeKey(
    node_id="sensor-node-2",
    key_id="sensor-node-2-v1",
    hmac_key=KEY,
    mac="88:13:BF:01:37:28",
)


class ServiceWifiTransportDiagnosticsTests(unittest.TestCase):
    def test_firmware_publishes_transport_and_wifi_counters(self) -> None:
        source = (
            ROOT
            / "firmware/sensor-node/components/service_wifi/src/service_wifi.cpp"
        ).read_text(encoding="utf-8")

        for field in (
            "heartbeat_send_attempts",
            "heartbeat_send_successes",
            "heartbeat_send_failures",
            "heartbeat_consecutive_send_failures",
            "heartbeat_max_consecutive_send_failures",
            "heartbeat_last_send_error",
            "wifi_disconnect_events",
            "wifi_got_ip_events",
            "wifi_last_disconnect_reason",
        ):
            self.assertIn(field, source)

        attempt = source.index("record_send_attempt();")
        send = source.index("const esp_err_t send_result = send_heartbeat();")
        result = source.index("record_send_result(send_result);")
        self.assertLess(attempt, send)
        self.assertLess(send, result)

    def test_diagnostics_do_not_change_heartbeat_period_or_success_sequence_rule(self) -> None:
        source = (
            ROOT
            / "firmware/sensor-node/components/service_wifi/src/service_wifi.cpp"
        ).read_text(encoding="utf-8")

        self.assertIn("constexpr std::uint32_t kHeartbeatPeriodMs = 10'000;", source)
        sent_check = source.index("if (sent != packet_length)")
        sequence_increment = source.index("++sequence_;")
        self.assertLess(sent_check, sequence_increment)

    def test_diagnostic_firmware_identifier_is_distinct(self) -> None:
        config = (
            ROOT
            / "firmware/sensor-node/components/config/include/config/firmware_config.hpp"
        ).read_text(encoding="utf-8")

        self.assertIn('kVersion[] = "0.6.1-stage1-transport-diag"', config)
        self.assertIn('kProductionBaselineVersion[] = "0.6.0-stage1-sen55-status"', config)
        self.assertIn("kFirmwareVersionPacked = 0x0006", config)

    def test_receiver_accepts_authenticated_transport_extension_fields(self) -> None:
        payload = {
            "protocol": "WVC-HB1",
            "schema": 1,
            "node_id": "sensor-node-2",
            "key_id": "sensor-node-2-v1",
            "mac": "88:13:BF:01:37:28",
            "boot_id": "0123456789abcdef",
            "seq": 42,
            "firmware": "0.6.1-stage1-transport-diag",
            "uptime_s": 420,
            "reset_reason": 1,
            "ota_partition": "ota_0",
            "ota_pending": False,
            "wifi_rssi_dbm": -51,
            "sensor_state": "running",
            "measurement_age_ms": 120,
            "sensor_last_error": 0,
            "sensor_detection_failures": 0,
            "sensor_communication_failures": 0,
            "sensor_crc_failures": 0,
            "sensor_successful_measurements": 400,
            "rs485_ready": True,
            "modbus_slave": 2,
            "modbus_monitor_ready": True,
            "modbus_requests_total": 200,
            "modbus_requests_last_60s": 56,
            "last_modbus_request_age_ms": 250,
            "modbus_service_errors": 0,
            "heartbeat_send_attempts": 43,
            "heartbeat_send_successes": 42,
            "heartbeat_send_failures": 0,
            "heartbeat_consecutive_send_failures": 0,
            "heartbeat_max_consecutive_send_failures": 0,
            "heartbeat_last_send_error": 0,
            "wifi_disconnect_events": 0,
            "wifi_got_ip_events": 1,
            "wifi_last_disconnect_reason": 0,
        }

        decoded = decode_and_authenticate_frame(
            encode_frame(payload, KEY),
            source_ip="10.55.0.110",
            keys={NODE_KEY.node_id: NODE_KEY},
        )

        self.assertEqual(decoded["heartbeat_send_attempts"], 43)
        self.assertEqual(decoded["wifi_got_ip_events"], 1)
        self.assertEqual(decoded["firmware"], "0.6.1-stage1-transport-diag")


if __name__ == "__main__":
    unittest.main()
