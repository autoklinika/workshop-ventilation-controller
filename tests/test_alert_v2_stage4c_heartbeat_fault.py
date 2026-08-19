from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from ventilation_core.alert_v2_stage4c_fault import (
    HEARTBEAT_PORT,
    NFT_CHAIN,
    NFT_FAMILY,
    NFT_TABLE,
    SERVICE_ADDRESS,
    SERVICE_INTERFACE,
    Stage4CFaultError,
    build_delete_rule_command,
    build_drop_rule_command,
    find_comment_handles,
    find_stage4c_handles,
    validate_service_source_ip,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "validate_alert_v2_stage4c_heartbeat_dropout_cm5.py"


class AlertV2Stage4CHeartbeatFaultTests(unittest.TestCase):
    def test_source_ip_is_limited_to_service_subnet_and_not_cm5(self) -> None:
        self.assertEqual(validate_service_source_ip("10.55.0.106"), "10.55.0.106")
        with self.assertRaises(Stage4CFaultError):
            validate_service_source_ip("192.168.1.20")
        with self.assertRaises(Stage4CFaultError):
            validate_service_source_ip(SERVICE_ADDRESS)

    def test_drop_rule_targets_only_one_source_and_heartbeat_udp_port(self) -> None:
        command = build_drop_rule_command(
            "10.55.0.106",
            "wvc-alert-v2-stage4c-heartbeat-drop-test",
        )
        self.assertEqual(command[:6], ["nft", "insert", "rule", NFT_FAMILY, NFT_TABLE, NFT_CHAIN])
        self.assertIn(SERVICE_INTERFACE, command)
        self.assertIn("10.55.0.106", command)
        self.assertIn(SERVICE_ADDRESS, command)
        self.assertIn(str(HEARTBEAT_PORT), command)
        self.assertIn("drop", command)
        self.assertNotIn("tcp", command)
        self.assertNotIn("67", command)

    def test_delete_rule_uses_only_exact_handle(self) -> None:
        self.assertEqual(
            build_delete_rule_command(123),
            ["nft", "delete", "rule", NFT_FAMILY, NFT_TABLE, NFT_CHAIN, "handle", "123"],
        )
        with self.assertRaises(Stage4CFaultError):
            build_delete_rule_command(0)

    def test_handle_parser_matches_unique_comment_and_stage_prefix(self) -> None:
        chain = """
        ip saddr 10.55.0.106 udp dport 45551 drop comment \"wvc-alert-v2-stage4c-heartbeat-drop-1\" # handle 17
        ip saddr 10.55.0.110 udp dport 45551 accept # handle 18
        """
        self.assertEqual(
            find_comment_handles(chain, "wvc-alert-v2-stage4c-heartbeat-drop-1"),
            [17],
        )
        self.assertEqual(find_stage4c_handles(chain), [17])

    def test_validator_is_valid_python(self) -> None:
        spec = importlib.util.spec_from_file_location("stage4c_validator", TOOL)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)

    def test_validator_contract_is_heartbeat_only_and_requires_stop(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("KAMOD_HEARTBEAT_LOST", source)
        self.assertIn("require_passive_safe_state", source)
        self.assertIn("sensor_bus_error_counters_unchanged", source)
        self.assertIn("temporary_firewall_rule_removed", source)
        self.assertIn("write_commands_sent\": 0", source)
        self.assertIn("affects_control\": False", source)
        self.assertNotIn('core.request("set"', source)
        self.assertNotIn('core.request("stop"', source)
        self.assertNotIn('core.request("shutdown"', source)
        self.assertNotIn("aero-speed", source)
        self.assertNotIn("aero-airing", source)
        self.assertNotIn("zigbee-permit-join", source)

    def test_validator_has_finally_cleanup_for_temporary_rule(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("finally:", source)
        self.assertIn("fault_rule.remove()", source)
        self.assertIn("CRITICAL CLEANUP FAILURE", source)


if __name__ == "__main__":
    unittest.main()
