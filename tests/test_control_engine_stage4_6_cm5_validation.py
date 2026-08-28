from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage4_6_cm5.sh"


class ControlEngineStage46Cm5ValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_harness_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_every_embedded_python_validator_compiles(self) -> None:
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY\n", self.text, flags=re.DOTALL)
        self.assertEqual(len(blocks), 4)
        for index, block in enumerate(blocks):
            with self.subTest(index=index):
                compile(block, f"{HARNESS.name}:heredoc-{index}", "exec")

    def test_harness_pins_production_main_and_exact_ci_tested_branch(self) -> None:
        self.assertIn(
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            self.text,
        )
        self.assertIn(
            'EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE46_EXPECTED_BRANCH_SHA:-}"',
            self.text,
        )
        self.assertIn(
            "git ls-remote --exit-code origin refs/heads/main",
            self.text,
        )
        self.assertIn(
            'git ls-remote --exit-code origin "refs/heads/$BRANCH"',
            self.text,
        )
        self.assertIn('[ "$MAIN_LS_REMOTE" = "$EXPECTED_BASE" ]', self.text)
        self.assertIn('[ "$BRANCH_LS_REMOTE" = "$EXPECTED_BRANCH_SHA" ]', self.text)
        self.assertIn('git fetch --no-tags origin main "$BRANCH"', self.text)
        self.assertIn('[ "$MAIN_REMOTE" = "$EXPECTED_BASE" ]', self.text)
        self.assertIn('[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ]', self.text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', self.text)
        self.assertIn('[ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ]', self.text)

    def test_preflight_requires_existing_zero_output_and_never_commands_actuators(self) -> None:
        self.assertIn('require_zero_output_guard "$ROOT/src" "production preflight"', self.text)
        self.assertIn('sp.get("supply_voltage") != 0.0', self.text)
        self.assertIn('sp.get("extract_voltage") != 0.0', self.text)
        self.assertIn('float(row.get("rpm") or 0.0) != 0.0', self.text)
        self.assertGreaterEqual(self.text.count("require_zero_output_guard"), 5)

        for forbidden in (
            'ctl "$WT/src" set',
            'ctl "$ROOT/src" set',
            'ctl "$WT/src" stop',
            'ctl "$ROOT/src" stop',
            'ctl "$WT/src" aero-speed',
            'ctl "$WT/src" aero-airing',
            'ctl "$WT/src" shutdown',
            "systemctl poweroff",
            "systemctl reboot",
            "/usr/bin/systemctl poweroff",
            "/usr/bin/systemctl reboot",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_scheduled_shutdown_is_explicitly_rejected_not_enabled(self) -> None:
        self.assertIn("*--enable-scheduled-shutdown*)", self.text)
        self.assertIn("scheduled shutdown unexpectedly enabled", self.text)
        self.assertIn("exit 1", self.text)
        self.assertNotIn("Environment=ENABLE_SCHEDULED_SHUTDOWN", self.text)
        self.assertNotIn("Environment=WVC_ENABLE_SCHEDULED_SHUTDOWN", self.text)

    def test_manual_intent_is_shadow_only_and_returned_to_auto(self) -> None:
        for expected in (
            '"mode": "MANUAL"',
            '"manual_supply_pct": 37.0',
            '"manual_extract_pct": 43.0',
            '"manual_aero_speed": 2',
            'ctl "$WT/src" control-engine-operator-replace --file "$TEST_ROOT/manual.json"',
            "assert_operator_state MANUAL 1",
            "assert_shadow_operator_manual",
            'ctl "$WT/src" control-engine-operator-replace --file "$TEST_ROOT/auto.json"',
            "assert_operator_state AUTO 2",
            'shadow.get("actuation_supported") is not False',
            'zone.get("proposed_supply_voltage") is not None',
            'zone.get("proposed_extract_voltage") is not None',
        ):
            self.assertIn(expected, self.text)

    def test_restart_must_reset_volatile_manual_intent_to_auto_revision_zero(self) -> None:
        self.assertIn("===== 5. CORE RESTART MUST RESET OPERATOR INTENT =====", self.text)
        self.assertGreaterEqual(self.text.count('sudo systemctl restart "$CORE_UNIT"'), 3)
        self.assertGreaterEqual(self.text.count("assert_operator_state AUTO 0"), 2)
        for expected in (
            'operator.get("persistent") is not False',
            'operator.get("reset_on_core_restart") is not True',
            'operator.get("actuation_supported") is not False',
        ):
            self.assertIn(expected, self.text)

    def test_tacho_is_not_required_at_actual_zero_volts(self) -> None:
        for expected in (
            'zone1.get(f"tacho_{channel}_feedback_required") is not False',
            'zone1.get(f"tacho_{channel}_status") != "NOT_REQUIRED"',
            'zone1.get(f"tacho_{channel}_fault_confirmed") is not False',
            "TACHO remained NOT_REQUIRED at actual 0 V",
        ):
            self.assertIn(expected, self.text)
        self.assertGreaterEqual(self.text.count("assert_shadow_zero_tacho"), 4)

    def test_host_rtc_and_production_checkout_are_protected(self) -> None:
        for expected in (
            'BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"',
            'HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"',
            'HOST_POWER_STATUS_BEFORE="$(systemctl show wvc-host-power.service -p StatusText --value)"',
            'WAKEALARM_BEFORE="$(read_wakealarm)"',
            '[ "$boot_id" = "$BOOT_ID_BEFORE" ]',
            '[ "$host_pid" = "$HOST_POWER_PID_BEFORE" ]',
            '[ "$host_status" = "$HOST_POWER_STATUS_BEFORE" ]',
            '[ "$wakealarm" = "$WAKEALARM_BEFORE" ]',
            '[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ]',
            '[ -z "$(git status --short)" ]',
        ):
            self.assertIn(expected, self.text)
        self.assertGreaterEqual(self.text.count("assert_host_not_touched"), 5)

    def test_branch_runtime_uses_only_worktree_and_environment_dropin(self) -> None:
        self.assertIn("WorkingDirectory=$WT", self.text)
        self.assertIn("Environment=PYTHONPATH=$WT/src", self.text)
        self.assertNotIn("ExecStart=", self.text)
        self.assertIn('[ "$cwd" = "$WT" ]', self.text)

    def test_failure_path_restores_production_core_and_removes_dropin(self) -> None:
        for expected in (
            "trap emergency_rollback EXIT INT TERM",
            'sudo rm -f "$CORE_DROPIN"',
            'sudo systemctl daemon-reload',
            'sudo systemctl restart "$CORE_UNIT"',
            'git -C "$ROOT" worktree remove --force "$WT"',
            '[ "$cwd" != "$ROOT" ]',
        ):
            self.assertIn(expected, self.text)


if __name__ == "__main__":
    unittest.main()
