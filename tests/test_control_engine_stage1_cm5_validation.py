from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage1_cm5.sh"


class ControlEngineStage1Cm5ValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_harness_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_harness_pins_production_main_and_exact_ci_tested_branch(self) -> None:
        self.assertIn(
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            self.text,
        )
        self.assertIn(
            'EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_EXPECTED_BRANCH_SHA:-}"',
            self.text,
        )
        self.assertIn('git fetch origin main "$BRANCH"', self.text)
        self.assertIn('[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ]', self.text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', self.text)

    def test_branch_core_cannot_opt_in_to_scheduled_shutdown(self) -> None:
        exec_lines = [
            line
            for line in self.text.splitlines()
            if line.startswith("ExecStart=/usr/bin/python3 -B -m ventilation_core.main")
        ]
        self.assertEqual(len(exec_lines), 1)
        self.assertNotIn("--enable-scheduled-shutdown", exec_lines[0])
        self.assertIn("--power-scheduler-poll-interval 1.0", exec_lines[0])
        self.assertIn(
            'grep -q -- "--enable-scheduled-shutdown" "$WT/deploy/systemd/ventilation-core.service"',
            self.text,
        )
        self.assertIn(
            'echo "FAIL: production systemd unit unexpectedly enables scheduled shutdown"',
            self.text,
        )

    def test_harness_requires_zero_output_and_no_observed_fan_motion(self) -> None:
        self.assertIn('sp.get("supply_voltage") != 0.0', self.text)
        self.assertIn('sp.get("extract_voltage") != 0.0', self.text)
        self.assertIn('mode not in {"STOP", "FAULT"}', self.text)
        self.assertIn('float(row.get("rpm") or 0.0) != 0.0', self.text)
        self.assertIn('value not in (None, 0)', self.text)
        self.assertGreaterEqual(self.text.count("require_safe_state"), 5)

    def test_harness_proves_host_rtc_and_boot_are_untouched(self) -> None:
        self.assertIn('BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"', self.text)
        self.assertIn('HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"', self.text)
        self.assertIn('WAKEALARM_BEFORE="$(read_wakealarm)"', self.text)
        self.assertIn('[ "$boot_id" = "$BOOT_ID_BEFORE" ]', self.text)
        self.assertIn('[ "$host_pid" = "$HOST_POWER_PID_BEFORE" ]', self.text)
        self.assertIn('[ "$wakealarm" = "$WAKEALARM_BEFORE" ]', self.text)
        self.assertIn('*"12 V domain ON"*', self.text)
        for forbidden in (
            "systemctl --no-block poweroff",
            "systemctl --no-block reboot",
            "/usr/bin/systemctl poweroff",
            "/usr/bin/systemctl reboot",
            'ctl "$WT/src" shutdown',
        ):
            self.assertNotIn(forbidden, self.text)
        for required_call in (
            'assert_host_not_touched "Control Engine branch first boot"',
            'assert_host_not_touched "after Control Engine hot reload"',
            'assert_host_not_touched "Control Engine branch after restart"',
            'assert_host_not_touched "final production main"',
        ):
            self.assertIn(required_call, self.text)

    def test_control_engine_remains_persistent_shadow_without_actuation(self) -> None:
        for expected in (
            'ce.get("actuation_supported") is not False',
            'shadow.get("actuation_supported") is not False',
            'shadow.get("configuration_revision") != revision',
            'shadow.get("configuration_persistent") is not True',
            'zone.get("proposed_supply_voltage") is not None',
            'zone.get("proposed_extract_voltage") is not None',
            'any(value is not None for value in tuning.values())',
        ):
            self.assertIn(expected, self.text)
        self.assertIn('"actuation_enabled" in config', self.text)
        self.assertIn('"actuation_enabled" in policy', self.text)

    def test_hot_reload_changes_only_version_then_survives_restart(self) -> None:
        self.assertIn(
            'config["policy"]["version"] = "control-engine-stage1-cm5-validation"',
            self.text,
        )
        self.assertIn('control-engine-replace --file "$TEST_ROOT/control-engine-v2.json"', self.text)
        self.assertIn('ce.get("revision") != 2', self.text)
        self.assertIn('ce.get("dynamics_reset") is not True', self.text)
        self.assertIn(
            'require_control_engine_state 2 "control-engine-stage1-cm5-validation" "after hot reload"',
            self.text,
        )
        self.assertIn(
            'require_control_engine_state 2 "control-engine-stage1-cm5-validation" "after branch core restart"',
            self.text,
        )
        self.assertIn('[ "$BRANCH_PID_2" != "$BRANCH_PID_1" ]', self.text)

    def test_failure_path_restores_production_main_and_cleans_worktree(self) -> None:
        self.assertIn("trap emergency_rollback EXIT INT TERM", self.text)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', self.text)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.text)
        self.assertIn('unit_cwd "$MAIN_PID_AFTER")" = "$ROOT"', self.text)
        self.assertIn('[ "$(git -C "$ROOT" branch --show-current)" = "main" ]', self.text)
        self.assertIn('[ "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_BASE" ]', self.text)
        self.assertIn('sudo find "$WT" -type d -name __pycache__', self.text)
        self.assertIn("ROLLOUT_STARTED=0", self.text)


if __name__ == "__main__":
    unittest.main()
