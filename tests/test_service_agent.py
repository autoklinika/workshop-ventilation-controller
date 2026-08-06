from __future__ import annotations

import unittest

from ventilation_core.service_agent import (
    CommandResult,
    ServiceAgentState,
    probe_service_network,
)
from ventilation_core.service_heartbeat import NodeKey


class ServiceAgentStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = {
            "sensor-node-1": NodeKey(
                node_id="sensor-node-1",
                key_id="key-1",
                hmac_key=b"1" * 32,
                mac="88:13:BF:00:52:D0",
            ),
            "sensor-node-2": NodeKey(
                node_id="sensor-node-2",
                key_id="key-2",
                hmac_key=b"2" * 32,
                mac="88:13:BF:01:37:28",
            ),
        }

    def test_registered_nodes_start_offline(self) -> None:
        state = ServiceAgentState(self.keys)

        nodes = state.nodes()

        self.assertEqual([node["node_id"] for node in nodes], ["sensor-node-1", "sensor-node-2"])
        self.assertFalse(nodes[0]["online"])
        self.assertFalse(nodes[1]["online"])
        self.assertIsNone(nodes[0]["heartbeat"])

    def test_authenticated_persisted_state_is_normalised(self) -> None:
        state = ServiceAgentState(self.keys)
        heartbeat = {
            "node_id": "sensor-node-1",
            "mac": "88:13:BF:00:52:D0",
            "firmware": "0.4.0-stage1",
            "uptime_s": 123,
            "wifi_rssi_dbm": -42,
            "sensor_state": "running",
            "measurement_age_ms": 250,
            "rs485_ready": True,
            "modbus_monitor_ready": True,
            "modbus_slave": 1,
            "modbus_requests_total": 500,
            "modbus_requests_last_60s": 58,
            "last_modbus_request_age_ms": 300,
            "ota_partition": "ota_0",
            "ota_pending": False,
        }

        state.record(
            {
                "online": True,
                "received_unix_ms": 123456789,
                "source_ip": "10.55.0.106",
                "heartbeat": heartbeat,
            }
        )
        node = state.nodes()[0]

        self.assertTrue(node["online"])
        self.assertEqual(node["source_ip"], "10.55.0.106")
        self.assertEqual(node["modbus_address"], 1)
        self.assertEqual(node["wifi_rssi_dbm"], -42)
        self.assertTrue(node["rs485_ready"])
        self.assertEqual(node["heartbeat"], heartbeat)

    def test_expiration_marks_only_selected_node_offline(self) -> None:
        state = ServiceAgentState(self.keys)
        for node_id, source_ip in (
            ("sensor-node-1", "10.55.0.106"),
            ("sensor-node-2", "10.55.0.110"),
        ):
            state.record(
                {
                    "online": True,
                    "received_unix_ms": 123,
                    "source_ip": source_ip,
                    "heartbeat": {"node_id": node_id},
                }
            )

        state.mark_offline(["sensor-node-2"])
        nodes = {node["node_id"]: node for node in state.nodes()}

        self.assertTrue(nodes["sensor-node-1"]["online"])
        self.assertFalse(nodes["sensor-node-2"]["online"])
        self.assertIsNone(nodes["sensor-node-2"]["source_ip"])

    def test_unknown_persisted_node_is_rejected(self) -> None:
        state = ServiceAgentState(self.keys)

        with self.assertRaisesRegex(ValueError, "unknown node"):
            state.record(
                {
                    "online": True,
                    "heartbeat": {"node_id": "sensor-node-3"},
                }
            )


class ServiceNetworkProbeTests(unittest.TestCase):
    def test_ready_requires_ap_address_dhcp_and_firewall(self) -> None:
        results = {
            ("nmcli", "-g", "GENERAL.CONNECTION", "device", "show", "wlan0"): CommandResult(0, "wvc-sensor-service"),
            ("nmcli", "-g", "GENERAL.STATE", "device", "show", "wlan0"): CommandResult(0, "100 (connected)"),
            ("nmcli", "-g", "IP4.ADDRESS", "device", "show", "wlan0"): CommandResult(0, "10.55.0.1/24"),
            ("systemctl", "is-active", "wvc-sensor-dhcp.service"): CommandResult(0, "active"),
            ("systemctl", "is-active", "wvc-sensor-firewall.service"): CommandResult(0, "active"),
        }

        state = probe_service_network(results.__getitem__)

        self.assertTrue(state.ready)
        self.assertTrue(state.ap_active)
        self.assertTrue(state.address_present)
        self.assertTrue(state.dhcp_active)
        self.assertTrue(state.firewall_active)

    def test_network_is_not_ready_when_dhcp_is_down(self) -> None:
        def runner(command: tuple[str, ...]) -> CommandResult:
            if command == ("systemctl", "is-active", "wvc-sensor-dhcp.service"):
                return CommandResult(3, "inactive")
            if command[0] == "nmcli" and "CONNECTION" in command[2]:
                return CommandResult(0, "wvc-sensor-service")
            if command[0] == "nmcli" and "STATE" in command[2]:
                return CommandResult(0, "100 (connected)")
            if command[0] == "nmcli" and "IP4.ADDRESS" in command[2]:
                return CommandResult(0, "10.55.0.1/24")
            return CommandResult(0, "active")

        state = probe_service_network(runner)

        self.assertFalse(state.ready)
        self.assertFalse(state.dhcp_active)
        self.assertTrue(state.firewall_active)


if __name__ == "__main__":
    unittest.main()
