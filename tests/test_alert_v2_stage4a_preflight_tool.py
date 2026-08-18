from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/validate_alert_v2_stage4a_preflight.py"


class AlertV2Stage4APreflightToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = TOOL.read_text(encoding="utf-8")

    def test_tool_is_valid_python(self) -> None:
        compile(self.source, str(TOOL), "exec")

    def test_tool_allows_only_read_only_core_commands(self) -> None:
        self.assertIn('{"command": "status"}', self.source)
        self.assertIn('{"command": "sensors"}', self.source)
        self.assertIn('command not in {"status", "sensors"}', self.source)

        forbidden = (
            '"command": "set"',
            '"command": "stop"',
            '"command": "shutdown"',
            '"command": "ack-alert"',
            '"command": "aero-speed"',
            '"command": "aero-airing"',
            '"command": "schedule-replace"',
            '"command": "zigbee-permit-join"',
            '"command": "zigbee-remove-device"',
            'ota-install',
        )
        for token in forbidden:
            self.assertNotIn(token, self.source)

    def test_tool_requires_stop_zero_and_known_output_state(self) -> None:
        self.assertIn('state.get("mode") != "STOP"', self.source)
        self.assertIn('supply != 0.0 or extract != 0.0', self.source)
        self.assertIn('state.get("output_state_known") is not True', self.source)
        self.assertIn('"write_commands_sent": 0', self.source)

    def test_tool_requires_exact_live_node_mapping(self) -> None:
        self.assertIn('"sensor-node-1": 1', self.source)
        self.assertIn('"sensor-node-2": 2', self.source)
        self.assertIn('mapping != EXPECTED_NODE_MAPPING', self.source)
        self.assertIn('addresses != [1, 2]', self.source)

    def test_tool_exercises_real_branch_correlator_without_control(self) -> None:
        self.assertIn("ServicePlaneCorrelatingAlertRegistry", self.source)
        self.assertIn("ServicePlaneMonitor", self.source)
        self.assertIn('diagnostics.get("control_policy_applied") is not False', self.source)
        self.assertIn('correlation.get("derived_codes")', self.source)

    def test_tool_uses_bounded_local_socket_reads(self) -> None:
        self.assertIn("client.settimeout(timeout_seconds)", self.source)
        self.assertIn("MAX_CORE_RESPONSE_BYTES", self.source)
        self.assertIn("DEFAULT_SERVICE_AGENT_SOCKET", self.source)
        self.assertIn("--service-timeout", self.source)
        self.assertIn("default=0.35", self.source)


if __name__ == "__main__":
    unittest.main()
