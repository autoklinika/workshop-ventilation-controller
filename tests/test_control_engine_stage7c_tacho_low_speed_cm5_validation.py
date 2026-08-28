from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage7c_tacho_low_speed_cm5.sh"


class Stage7CTachoLowSpeedHarnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_harness_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_harness_pins_exact_ci_tested_branch_and_production_main(self) -> None:
        self.assertIn(
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            self.text,
        )
        self.assertIn(
            'EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE7C_EXPECTED_BRANCH_SHA:-}"',
            self.text,
        )
        self.assertIn("git ls-remote origin refs/heads/main", self.text)
        self.assertIn('git ls-remote origin "refs/heads/$BRANCH"', self.text)
        self.assertIn('[ "$BRANCH_LS_REMOTE" = "$EXPECTED_BRANCH_SHA" ]', self.text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', self.text)

    def test_harness_requires_explicit_physical_confirmation(self) -> None:
        self.assertIn(
            'CONTROL_ENGINE_STAGE7C_CONFIRM_PHYSICAL_FAN_SPIN:-',
            self.text,
        )
        self.assertIn('[ "$CONFIRM_PHYSICAL_SPIN" = "YES" ]', self.text)
        self.assertIn("WARNING: this test intentionally runs both local EC fans at 1.0 V", self.text)
        self.assertIn("--confirm-fan-spin-test", self.text)

    def test_scope_is_three_full_low_speed_cycles(self) -> None:
        for expected in (
            "--test-voltage 1.0",
            "--hold-seconds 20.0",
            "--cycles 3",
            "--rest-seconds 3.0",
            "--tail-window 7.0",
            "20 s x 3 cycles",
        ):
            self.assertIn(expected, self.text)

    def test_harness_reuses_characterization_validator_without_writing_tuning(self) -> None:
        self.assertIn(
            '"$WT/tools/validate_control_engine_stage7b_tacho_characterization_cm5.py"',
            self.text,
        )
        self.assertIn("no tuning value was written automatically", self.text)
        self.assertNotIn("control-engine-replace", self.text)
        self.assertNotIn("aero-speed", self.text)
        self.assertNotIn("aero-airing", self.text)

    def test_harness_preserves_shadow_boundary_and_host_power(self) -> None:
        self.assertIn('shadow.get("actuation_supported") is not False', self.text)
        self.assertIn("assert_host_untouched", self.text)
        self.assertIn('WAKEALARM_BEFORE="$(read_wakealarm)"', self.text)
        self.assertIn("*--enable-scheduled-shutdown*)", self.text)
        for forbidden in (
            "systemctl poweroff",
            "systemctl reboot",
            "/sbin/poweroff",
            "/sbin/reboot",
            'ctl "$WT/src" shutdown',
            'ctl "$ROOT/src" shutdown',
        ):
            self.assertNotIn(forbidden, self.text)

    def test_cleanup_always_returns_to_zero_and_production_runtime(self) -> None:
        self.assertIn("trap emergency_rollback EXIT INT TERM", self.text)
        self.assertIn('ctl "$WT/src" stop', self.text)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', self.text)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.text)
        self.assertIn('[ "$cwd" != "$ROOT" ]', self.text)
        self.assertIn('sp.get("supply_voltage") != 0.0', self.text)
        self.assertIn('sp.get("extract_voltage") != 0.0', self.text)


if __name__ == "__main__":
    unittest.main()
