from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "validate_alert_v2_stage4d_node_power_loss_cm5.py"


class AlertV2Stage4DNodePowerLossTests(unittest.TestCase):
    def test_validator_is_valid_python_module(self) -> None:
        spec = importlib.util.spec_from_file_location("stage4d_validator", TOOL)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)

    def test_validator_requires_explicit_manual_power_cycle_confirmation(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("--confirm-manual-power-cycle", source)
        self.assertIn("can be powered off independently", source)
        self.assertIn("POWER OFF ONLY", source)
        self.assertIn("RESTORE POWER", source)
        self.assertGreaterEqual(source.count("input("), 2)

    def test_validator_expects_real_production_then_correlated_alert(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn('PRODUCTION_ALERT = "SENSOR_NODE_UNAVAILABLE"', source)
        self.assertIn('CORRELATED_ALERT = "KAMOD_NODE_UNAVAILABLE"', source)
        self.assertIn('f"sensor-node:{target_address}:communication"', source)
        self.assertIn('f"sensor-node:{target_address}:correlated-unavailable"', source)
        self.assertIn("suppressed_legacy_keys", source)
        self.assertIn("production_test_incident_retained_in_history", source)

    def test_correlated_policy_contract_is_weight3_orange_and_read_only(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn('"weight": 3', source)
        self.assertIn('"hmi_color": "orange"', source)
        self.assertIn('"reaction": "fallback_local"', source)
        self.assertIn('"affects_control": True', source)
        self.assertIn('"control_policy_applied": False', source)
        self.assertIn('"write_commands_sent": 0', source)

    def test_validator_guards_non_target_and_stop_zero_state(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("require_passive_safe_state", source)
        self.assertIn("_require_non_target_healthy", source)
        self.assertIn("non-target SENSOR BUS", source)
        self.assertIn('"non_target_node_healthy": True', source)
        self.assertIn("both KAmod heartbeats must be online before Stage 4D", source)

    def test_validator_does_not_inject_software_or_issue_control_commands(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertNotIn('core.request("set"', source)
        self.assertNotIn('core.request("stop"', source)
        self.assertNotIn('core.request("shutdown"', source)
        self.assertNotIn("nft ", source)
        self.assertNotIn("nmcli ", source)
        self.assertNotIn("systemctl stop", source)
        self.assertNotIn("systemctl restart", source)
        self.assertNotIn("aero-speed", source)
        self.assertNotIn("aero-airing", source)
        self.assertNotIn("zigbee-permit-join", source)
        self.assertIn('"software_fault_injection": False', source)

    def test_interrupted_test_prints_manual_recovery_instruction(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("finally:", source)
        self.assertIn("ACTION REQUIRED FOR RECOVERY", source)
        self.assertIn("Stage 4D cannot restore physical power", source)
        self.assertIn("Ensure power is restored", source)

    def test_recovery_requires_both_paths_and_cleared_history_record(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("target_sensor_healthy", source)
        self.assertIn("target_heartbeat_healthy", source)
        self.assertIn("production_alert_cleared", source)
        self.assertIn("correlated_cleared", source)
        self.assertIn("transitional_heartbeat_cleared", source)
        self.assertIn("cleared production SENSOR_NODE_UNAVAILABLE incident", source)
        self.assertIn('item.get("active") is False', source)
        self.assertIn('isinstance(item.get("cleared_at"), str)', source)


if __name__ == "__main__":
    unittest.main()
