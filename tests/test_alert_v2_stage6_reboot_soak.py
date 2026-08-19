from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "tools" / "validate_alert_v2_stage6_reboot_soak_cm5.py"


class AlertV2Stage6RebootSoakTests(unittest.TestCase):
    def test_validator_is_valid_python(self) -> None:
        ast.parse(VALIDATOR.read_text(encoding="utf-8"))

    def test_validator_has_prepare_and_verify_phases(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("prepare"', source)
        self.assertIn('sub.add_parser("verify"', source)
        self.assertIn("boot_id did not change", source)
        self.assertIn("Stage 6 pre-reboot baseline recorded", source)

    def test_validator_uses_only_read_only_core_commands(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("CoreReadOnlyClient", source)
        self.assertIn('client.request("status")', source)
        self.assertIn('client.request("alerts"', source)
        for forbidden in (
            'request("set"',
            'request("stop"',
            'request("shutdown"',
            "aero-speed",
            "aero-airing",
            "zigbee-permit-join",
            "zigbee-request-remove-device",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"control_commands_sent_by_validator": 0', source)
        self.assertIn('"automatic_alertv2_control_enabled": False', source)

    def test_web_checks_are_get_only_and_narrow(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('method="GET"', source)
        self.assertNotIn('method="POST"', source)
        self.assertIn('"/api/v1/state"', source)
        self.assertIn('"/api/v1/alerts"', source)
        self.assertIn('"/api/v1/health"', source)
        self.assertIn("Stage 6 forbids web path", source)

    def test_reboot_validation_requires_stage5_runtime_and_policy_persistence(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('DEFAULT_EXPECTED_RUNTIME = Path("/home/wentylacja/wvc-alert-v2-stage4")', source)
        self.assertIn('DEFAULT_POLICY = Path("/etc/workshop-ventilation/alerts-v2.toml")', source)
        self.assertIn("runtime policy changed across reboot", source)
        self.assertIn("Stage 5 runtime did not persist across reboot", source)
        self.assertIn("EXPECTED_ALERT_COUNT = 49", source)

    def test_soak_requires_stop_zero_read_only_mapping_and_stable_pids(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("require_passive_safe_state", source)
        self.assertIn('"runtime_mode": "read_only_mapping"', source)
        self.assertIn('"control_policy_applied": False', source)
        self.assertIn('"unmapped_active_alerts": 0', source)
        self.assertIn("production core PID changed during Stage 6 soak", source)
        self.assertIn("Service Agent PID changed during Stage 6 soak", source)

    def test_alert_history_persistence_is_checked_without_mutation(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("persistence_incident_ids", source)
        self.assertIn("alert lifecycle history lost across reboot", source)
        self.assertNotIn("ack-alert", source)
        self.assertNotIn("clear-alert", source)
        self.assertNotIn("alerts.sqlite3", source)

    def test_hmi_comm_watchdog_is_only_documented_automatic_exception(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn(
            '"hmi_cm5_communication_watchdog_remains_separate_local_exception": True',
            source,
        )
        self.assertIn('"reaction_execution_enabled": False', source)


if __name__ == "__main__":
    unittest.main()
