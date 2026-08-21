from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_pr77_runtime_active_to_off_cm5.sh"


class Pr77RuntimeValidationHarnessTests(unittest.TestCase):
    def test_harness_has_valid_shell_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_harness_runs_branch_core_via_temporary_dropin_and_restores_main(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("WorkingDirectory=%s", source)
        self.assertIn("Environment=PYTHONPATH=%s/src", source)
        self.assertIn('"$WT" "$WT"', source)
        self.assertIn('sudo tee "$DROPIN_PATH"', source)
        self.assertIn('sudo systemctl restart "$UNIT"', source)
        self.assertIn('sudo rm -f "$DROPIN_PATH"', source)
        self.assertIn("emergency_rollback", source)
        self.assertIn("trap emergency_rollback EXIT INT TERM", source)
        self.assertIn('unit_cwd "$BRANCH_PID"', source)
        self.assertIn('unit_cwd "$MAIN_PID_AFTER"', source)

    def test_harness_keeps_git_as_regular_user_and_scopes_privilege_to_systemd(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('git fetch origin main "$BRANCH"', source)
        self.assertIn('git worktree add --detach "$WT" "origin/$BRANCH"', source)
        self.assertNotIn("sudo git ", source)
        self.assertIn('sudo systemctl daemon-reload', source)
        self.assertIn('sudo systemctl restart "$UNIT"', source)

    def test_harness_executes_active_to_off_validator_and_requires_safe_states(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("validate_safe_shutdown_active_to_off_cm5.py", source)
        self.assertIn("--confirm-active-to-off-test", source)
        self.assertIn('require_safe_state "$ROOT/src" "preflight main"', source)
        self.assertIn('require_safe_state "$WT/src" "PR77 runtime before active test"', source)
        self.assertIn('require_safe_state "$WT/src" "PR77 runtime after active-to-off test"', source)
        self.assertIn('require_safe_state "$ROOT/src" "final production main"', source)
        self.assertIn('telemetry.get("fan_1_percent") != 0', source)
        self.assertIn('telemetry.get("fan_2_percent") != 0', source)

    def test_harness_never_powers_off_or_reboots_host(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("systemctl --no-block poweroff", source)
        self.assertNotIn("systemctl --no-block reboot", source)


if __name__ == "__main__":
    unittest.main()
