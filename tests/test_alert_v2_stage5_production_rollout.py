from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "tools" / "validate_alert_v2_stage5_production_read_only_cm5.py"
DEPLOY = REPO_ROOT / "tools" / "deploy_alert_v2_stage5_read_only_cm5.sh"


class AlertV2Stage5ProductionRolloutTests(unittest.TestCase):
    def test_validator_is_valid_python(self) -> None:
        ast.parse(VALIDATOR.read_text(encoding="utf-8"))

    def test_validator_uses_only_read_only_core_client(self) -> None:
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
        self.assertIn('"reaction_execution_enabled": False', source)

    def test_validator_requires_real_read_only_alert_v2_projection(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('"runtime_mode": "read_only_mapping"', source)
        self.assertIn('"loaded": True', source)
        self.assertIn('"control_policy_applied": False', source)
        self.assertIn('"unmapped_active_alerts": 0', source)
        self.assertIn("policy.policy_version", source)
        self.assertIn("policy.sha256", source)
        self.assertIn('"alert_count": policy.alert_count', source)
        self.assertNotIn("EXPECTED_ALERT_COUNT", source)
        self.assertIn('correlation.get("mode") != "read_only"', source)

    def test_validator_requires_stop_zero_and_stable_processes(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("require_passive_safe_state", source)
        self.assertIn('"ventilation-core.service"', source)
        self.assertIn('"wvc-service-agent.service"', source)
        self.assertIn("production ventilation-core PID changed", source)
        self.assertIn("Service Agent PID changed", source)
        self.assertIn("expected_worktree.resolve", source)

    def test_deploy_script_has_apply_status_and_rollback(self) -> None:
        source = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("apply) apply_rollout", source)
        self.assertIn("rollback) rollback_rollout", source)
        self.assertIn("status) status_rollout", source)
        self.assertIn("97-alert-v2-stage5-read-only.conf", source)
        self.assertIn("validate_alert_v2_stage4a_preflight.py", source)
        self.assertIn("validate_alert_v2_stage5_production_read_only_cm5.py", source)
        self.assertIn("STAGE 5 AUTOMATIC ROLLBACK", source)

    def test_deploy_dropin_does_not_replace_execstart_or_control_parameters(self) -> None:
        source = DEPLOY.read_text(encoding="utf-8")
        self.assertNotIn("ExecStart=", source)
        self.assertIn("WorkingDirectory=$WT", source)
        self.assertIn("Environment=PYTHONPATH=$WT/src", source)
        self.assertNotIn("--aero-write", source)
        self.assertNotIn("--enable-control", source)
        self.assertNotIn("--execute-reaction", source)

    def test_deploy_does_not_modify_alert_database_or_delete_policy_on_rollback(self) -> None:
        source = DEPLOY.read_text(encoding="utf-8")
        self.assertNotIn("alerts.sqlite3", source)
        self.assertNotIn('rm -f "$POLICY_PATH"', source)
        self.assertIn("existing runtime policy preserved", source)
        self.assertIn("POLICY_PATH was intentionally preserved", source)

    def test_deploy_requires_stop_zero_preflight_before_rollout_restart(self) -> None:
        source = DEPLOY.read_text(encoding="utf-8")
        apply_body = source.split("apply_rollout() {", 1)[1].split("rollback_rollout() {", 1)[0]
        preflight_index = apply_body.index("preflight\n")
        restart_index = apply_body.index('systemctl restart "$UNIT"')
        self.assertLess(preflight_index, restart_index)
        self.assertIn("validate_alert_v2_stage4a_preflight.py", source)


if __name__ == "__main__":
    unittest.main()
