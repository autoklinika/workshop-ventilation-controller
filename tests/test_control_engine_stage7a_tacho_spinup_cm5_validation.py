from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from tools.validate_control_engine_stage7a_tacho_spinup_cm5 import (
    inspect_channel,
    require_initial_safe_state,
)


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage7a_tacho_spinup_cm5.sh"
VALIDATOR = ROOT / "tools" / "validate_control_engine_stage7a_tacho_spinup_cm5.py"


def safe_state(*, actuation_supported: bool = False) -> dict[str, object]:
    return {
        "mode": "STOP",
        "hardware_ready": True,
        "output_state_known": True,
        "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
        "tacho": {
            "ready": True,
            "worker_alive": True,
            "supply": {"valid": False, "rpm": 0.0},
            "extract": {"valid": False, "rpm": 0.0},
        },
        "shadow_automation": {
            "actuation_supported": actuation_supported,
            "zones": [
                {
                    "zone": "zone-1",
                    "proposed_supply_voltage": None,
                    "proposed_extract_voltage": None,
                    "tacho_supply_status": "NOT_REQUIRED",
                    "tacho_supply_feedback_required": False,
                    "tacho_supply_fault_confirmed": False,
                    "tacho_extract_status": "NOT_REQUIRED",
                    "tacho_extract_feedback_required": False,
                    "tacho_extract_fault_confirmed": False,
                }
            ],
        },
    }


class Stage7ATachoSpinupValidatorTest(unittest.TestCase):
    def test_source_files_compile(self) -> None:
        compile(VALIDATOR.read_text(encoding="utf-8"), str(VALIDATOR), "exec")
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_initial_safe_state_requires_zero_output_ready_tacho_and_shadow_boundary(self) -> None:
        require_initial_safe_state(safe_state())

        bad = safe_state()
        bad["setpoints"] = {"supply_voltage": 2.0, "extract_voltage": 0.0}
        with self.assertRaises(RuntimeError):
            require_initial_safe_state(bad)

        bad = safe_state(actuation_supported=True)
        with self.assertRaises(RuntimeError):
            require_initial_safe_state(bad)

    def test_channel_is_healthy_only_when_raw_and_shadow_feedback_agree(self) -> None:
        state = safe_state()
        state["setpoints"] = {"supply_voltage": 2.0, "extract_voltage": 2.0}
        tacho = state["tacho"]
        assert isinstance(tacho, dict)
        tacho["supply"] = {"valid": True, "rpm": 1200.0}
        shadow = state["shadow_automation"]
        assert isinstance(shadow, dict)
        zone1 = shadow["zones"][0]
        zone1["tacho_supply_status"] = "HEALTHY"
        zone1["tacho_supply_feedback_required"] = True
        sample = inspect_channel(state, "supply")
        self.assertTrue(sample.healthy)

        zone1["tacho_supply_fault_confirmed"] = True
        self.assertFalse(inspect_channel(state, "supply").healthy)

    def test_harness_requires_explicit_physical_spin_confirmation(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn(
            'CONTROL_ENGINE_STAGE7A_CONFIRM_PHYSICAL_FAN_SPIN:-',
            text,
        )
        self.assertIn('[ "$CONFIRM_PHYSICAL_SPIN" = "YES" ]', text)
        self.assertIn("WARNING: this test intentionally commands both local EC fans to 2.0 V", text)
        self.assertIn("--confirm-fan-spin-test", text)

    def test_harness_pins_exact_sha_and_remote_refs(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn(
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            text,
        )
        self.assertIn(
            'EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE7A_EXPECTED_BRANCH_SHA:-}"',
            text,
        )
        self.assertIn("git ls-remote origin refs/heads/main", text)
        self.assertIn('git ls-remote origin "refs/heads/$BRANCH"', text)
        self.assertIn('[ "$BRANCH_LS_REMOTE" = "$EXPECTED_BRANCH_SHA" ]', text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', text)

    def test_physical_scope_is_low_speed_tacho_only(self) -> None:
        harness = HARNESS.read_text(encoding="utf-8")
        validator = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("--test-voltage 2.0", harness)
        self.assertIn("1.0 <= args.test_voltage <= 3.0", validator)
        self.assertIn('"command": "set"', validator)
        self.assertIn('"command": "stop"', validator)
        self.assertIn("finally:", validator)
        self.assertIn("_stop_and_verify", validator)
        self.assertIn("no Control Engine tuning value was written automatically", validator)
        self.assertNotIn("control-engine-replace", validator)
        self.assertNotIn("aero-speed", validator)
        self.assertNotIn("aero-airing", validator)

    def test_harness_never_powers_or_reboots_host(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        for forbidden in (
            "systemctl poweroff",
            "systemctl reboot",
            "/sbin/poweroff",
            "/sbin/reboot",
            'ctl "$WT/src" shutdown',
            'ctl "$ROOT/src" shutdown',
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("assert_host_untouched", text)
        self.assertIn('WAKEALARM_BEFORE="$(read_wakealarm)"', text)

    def test_scheduled_shutdown_is_rejected(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn("*--enable-scheduled-shutdown*)", text)
        self.assertIn("scheduled shutdown unexpectedly enabled", text)
        self.assertNotIn("Environment=WVC_ENABLE_SCHEDULED_SHUTDOWN", text)

    def test_cleanup_restores_zero_and_production_runtime(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn("trap emergency_rollback EXIT INT TERM", text)
        self.assertIn('ctl "$WT/src" stop', text)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', text)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', text)
        self.assertIn('[ "$cwd" != "$ROOT" ]', text)
        self.assertIn('sp.get("supply_voltage") != 0.0', text)
        self.assertIn('sp.get("extract_voltage") != 0.0', text)


if __name__ == "__main__":
    unittest.main()
