from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "tools" / "validate_heartbeat_service_only_cm5.py"
HARNESS = REPO_ROOT / "tools" / "install_validate_heartbeat_service_only_cm5.sh"


class HeartbeatServiceOnlyCm5ValidationTests(unittest.TestCase):
    def test_python_validator_is_importable(self) -> None:
        spec = importlib.util.spec_from_file_location("heartbeat_service_only_validator", VALIDATOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)

    def test_shell_harness_has_valid_bash_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_validator_proves_service_only_semantics_without_control(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('HEARTBEAT_ALERT = "KAMOD_HEARTBEAT_LOST"', source)
        self.assertIn('CORRELATED_NODE_ALERT = "KAMOD_NODE_UNAVAILABLE"', source)
        self.assertIn("service_only_offline_nodes", source)
        self.assertIn("HeartbeatDropRule.create", source)
        self.assertIn("temporary_firewall_rule_removed", source)
        self.assertIn("sensor_bus_error_counters_unchanged", source)
        self.assertIn("finally:", source)
        self.assertIn("fault_rule.remove()", source)
        self.assertIn('"control_commands_sent_by_validator": 0', source)
        self.assertNotIn('request("set"', source)
        self.assertNotIn('request("stop"', source)
        self.assertNotIn('request("shutdown"', source)
        self.assertNotIn("aero-speed", source)
        self.assertNotIn("aero-airing", source)

    def test_validator_accepts_natural_target_dropout_or_injects_when_online(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('validation_mode = "natural_dropout"', source)
        self.assertIn('validation_mode = "controlled_nft_dropout"', source)
        self.assertIn("using natural dropout as service-only validation evidence", source)
        self.assertIn("_observe_natural_or_wait_for_online", source)
        self.assertIn("continuing with controlled fault injection", source)
        self.assertNotIn("heartbeat must be online before fault injection", source)
        self.assertIn("natural target heartbeat dropout remained service-only", source)
        self.assertIn("controlled target heartbeat dropout remained service-only", source)

    def test_validator_tolerates_incidental_non_target_service_dropout(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("incidental_service_only_nodes", source)
        self.assertIn("incidental_service_only_nodes_observed", source)
        self.assertIn("incidental non-target heartbeat dropout remained service-only", source)
        self.assertNotIn("non-target {other_node} heartbeat went offline", source)
        self.assertIn("_require_no_heartbeat_operator_alert(client)", source)

    def test_target_recovery_is_observed_but_not_required_for_service_only_pass(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("target_recovered_during_validation", source)
        self.assertIn("observing optional service recovery", source)
        self.assertIn("this is service-only and does not fail", source)
        self.assertIn("no temporary heartbeat-drop nft rule remains", source)

    def test_harness_is_pinned_to_pr76_branch_and_restores_main(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        lower = source.lower()
        self.assertIn("BRANCH=agent/heartbeat-service-only-alert-policy", source)
        self.assertIn("EXPECTED_BASE=5fb252fdf2405cdcf76a1cc7b62e84140c678309", source)
        self.assertIn("98-heartbeat-service-only-validation.conf", source)
        self.assertIn("--target-node sensor-node-2", source)
        self.assertIn("rollback_to_main", source)
        self.assertIn("rm -f \"$DROPIN_PATH\"", source)
        self.assertIn("trap emergency_cleanup EXIT INT TERM", source)
        self.assertIn("require_passive_safe_state", source)
        self.assertNotIn("git checkout main", lower)
        self.assertNotIn("git switch main", lower)
        self.assertNotIn("git merge ", lower)
        self.assertNotIn("gh pr merge", lower)


if __name__ == "__main__":
    unittest.main()
