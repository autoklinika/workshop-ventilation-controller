from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import subprocess
import unittest

from ventilation_core.calendar import CalendarConfig, resolve_calendar


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_calendar_engine_m3_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_calendar_engine_m3_cm5.sh"
BRANCH = "agent/automation-v1-scheduler-assumptions"
MAIN_SHA = "7628c407cfc9c0ea72d262566759ea2d4598fec8"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("calendar_engine_m3_validator", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CalendarEngineM3Cm5ValidationTest(unittest.TestCase):
    def test_validator_is_valid_python_and_semantic_matrix_passes(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        compile(source, str(VALIDATOR), "exec")

        validator = load_validator_module()
        matrix = validator._validate_semantic_matrix()
        self.assertEqual(matrix["preventilation"]["phase"], "PREVENTILATION")
        self.assertEqual(matrix["active"]["phase"], "ACTIVE")
        self.assertEqual(matrix["purge"]["phase"], "PURGE")
        self.assertEqual(matrix["date_exception"]["rule_source"], "DATE_EXCEPTION")
        self.assertEqual(matrix["next_wake"]["next_wake"], "2026-08-31T06:30:00+02:00")

    def test_runtime_validation_config_is_safe_standby_today(self) -> None:
        validator = load_validator_module()
        config = CalendarConfig.from_dict(validator._runtime_safe_config())
        resolved = resolve_calendar(config, now_utc=datetime.now(timezone.utc)).to_dict()

        self.assertTrue(resolved["available"])
        self.assertEqual(resolved["phase"], "INACTIVE")
        self.assertEqual(resolved["effective_profile"], "M3_STANDBY")
        self.assertEqual(resolved["effective_mode"], "STANDBY")
        self.assertEqual(resolved["rule_source"], "DATE_EXCEPTION")
        self.assertIsNotNone(resolved["next_wake"])

    def test_validator_has_strict_non_control_command_allowlist(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('{"status", "calendar", "calendar-replace"}', source)
        self.assertIn("validator attempted forbidden core command", source)
        self.assertNotIn('"command": "set"', source)
        self.assertNotIn('"command": "stop"', source)
        self.assertNotIn('"command": "aero-speed"', source)
        self.assertNotIn('"command": "aero-airing"', source)
        self.assertNotIn('"command": "shutdown"', source)
        self.assertNotIn("HostPowerAgent", source)
        self.assertNotIn("systemctl", source)

    def test_validator_requires_shadow_to_remain_non_actuating(self) -> None:
        validator = load_validator_module()
        safe = {
            "mode": "STOP",
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "output_state_known": True,
            "automation": {"enabled": True, "actuation_supported": False},
            "tacho": {
                "supply": {"rpm": 0.0},
                "extract": {"rpm": 0.0},
            },
            "aero_bus": {
                "telemetry": {"fan_1_percent": 0, "fan_2_percent": 0},
            },
        }
        validator._require_non_actuating_safe_state(safe, "test")

        unsafe = dict(safe)
        unsafe["automation"] = {"enabled": True, "actuation_supported": True}
        with self.assertRaisesRegex(validator.ValidationError, "supports actuation"):
            validator._require_non_actuating_safe_state(unsafe, "test")

    def test_validator_lab_mode_accepts_fault_unknown_outputs_but_keeps_zero_output_guards(self) -> None:
        validator = load_validator_module()
        lab = {
            "mode": "FAULT",
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "output_state_known": False,
            "shadow_automation": {"enabled": True, "actuation_supported": False},
            "tacho": {
                "supply": {"rpm": 0.0},
                "extract": {"rpm": 0.0},
            },
            "aero_bus": {
                "telemetry": {"fan_1_percent": None, "fan_2_percent": None},
            },
        }
        validator._require_non_actuating_safe_state(lab, "lab", lab_mode=True)

        with self.assertRaisesRegex(validator.ValidationError, "mode is not STOP"):
            validator._require_non_actuating_safe_state(lab, "production", lab_mode=False)

        nonzero = dict(lab)
        nonzero["setpoints"] = {"supply_voltage": 1.0, "extract_voltage": 0.0}
        with self.assertRaisesRegex(validator.ValidationError, "EC outputs are not 0 V"):
            validator._require_non_actuating_safe_state(nonzero, "lab", lab_mode=True)

    def test_harness_has_valid_bash_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_harness_pins_main_and_runs_exact_fetched_branch_worktree(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn(f"BRANCH={BRANCH}", source)
        self.assertIn(f"EXPECTED_BASE={MAIN_SHA}", source)
        self.assertIn('EXPECTED_BRANCH_SHA="${M3_EXPECTED_BRANCH_SHA:-}"', source)
        self.assertIn('M3_EXPECTED_BRANCH_SHA must pin the exact CI-tested branch commit', source)
        self.assertIn('git fetch origin main "$BRANCH"', source)
        self.assertIn('BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"', source)
        self.assertIn('[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ]', source)
        self.assertIn('differs from CI-tested $EXPECTED_BRANCH_SHA', source)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', source)
        self.assertNotIn("sudo git ", source)

    def test_harness_uses_isolated_calendar_alert_and_zigbee_state(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("TEST_ROOT=/var/tmp/wvc-calendar-m3-validation", source)
        self.assertIn("--alerts-db $TEST_ROOT/alerts.sqlite3", source)
        self.assertIn("--automation-db $TEST_ROOT/automation.sqlite3", source)
        self.assertIn("--zigbee-roles-file $TEST_ROOT/zigbee-roles.json", source)
        self.assertIn("ExecStart=", source)
        self.assertIn("WorkingDirectory=$WT", source)
        self.assertIn("Environment=PYTHONPATH=$WT/src", source)
        self.assertIn('rm -rf "$TEST_ROOT"', source)

    def test_harness_stages_branch_webgui_on_separate_local_port(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("WEB_PORT=18092", source)
        self.assertIn("WVC_WEB_HOST=127.0.0.1", source)
        self.assertIn('PYTHONPATH="$WT/src"', source)
        self.assertIn("/usr/bin/python3 -m ventilation_core.web.main", source)
        self.assertIn('"$WEB_URL/api/v1/calendar"', source)
        self.assertNotIn("wvc-web-ui.service", source)

    def test_harness_checks_safe_state_before_during_after_and_restores_main(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('require_safe_state "$ROOT/src" "preflight production main"', source)
        self.assertIn('require_safe_state "$WT/src" "branch core before Calendar Engine writes"', source)
        self.assertIn('require_safe_state "$WT/src" "branch core after Calendar Engine writes"', source)
        self.assertIn('require_safe_state "$WT/src" "branch core after persistence restart"', source)
        self.assertIn('require_safe_state "$WT/src" "branch core after persistence verification"', source)
        self.assertIn('require_safe_state "$ROOT/src" "final production main"', source)
        self.assertIn('sudo rm -f "$DROPIN_PATH"', source)
        self.assertIn('sudo systemctl restart "$UNIT"', source)
        self.assertIn('unit_cwd "$MAIN_PID_AFTER"', source)

    def test_harness_lab_mode_accepts_disconnected_hardware_without_weakening_zero_output_guards(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('LAB_MODE="${M3_LAB_MODE:-0}"', source)
        self.assertIn('M3_LAB_MODE must be 0 or 1', source)
        self.assertIn('if lab_mode:', source)
        self.assertIn('if mode not in {"STOP", "FAULT"}', source)
        self.assertIn('EC logical setpoints are not 0 V', source)
        self.assertIn('automation unexpectedly supports actuation', source)
        self.assertIn('hardware readiness/output confirmation may be unavailable', source)
        self.assertIn('M3 LAB mode enabled; disconnected DAC/SEN55/AERO may leave core in FAULT/output_state_unknown', source)

    def test_harness_preflight_failure_does_not_restart_production_core(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("ROLLOUT_STARTED=0", source)
        self.assertIn('if [ "$ROLLOUT_STARTED" = "1" ]; then', source)
        self.assertIn('M3 stopped before rollout; production ventilation-core was not restarted by cleanup', source)
        self.assertIn("ROLLOUT_STARTED=1\nwrite_core_dropin", source)
        self.assertIn("ROLLOUT_STARTED=0\nremove_worktree_best_effort", source)

    def test_harness_performs_prepare_restart_verify_without_control_commands(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("--phase prepare", source)
        self.assertIn("--phase verify", source)
        self.assertIn('BRANCH_PID_VERIFY="$(unit_pid)"', source)
        self.assertIn('"$BRANCH_PID_VERIFY" != "$BRANCH_PID_PREPARE"', source)
        self.assertNotIn("aero-speed", source)
        self.assertNotIn("aero-airing", source)
        self.assertNotIn("ventilation_core.ctl stop", source)
        self.assertNotIn('ctl "$src" stop', source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("systemctl --no-block poweroff", source)
        self.assertNotIn("systemctl --no-block reboot", source)


if __name__ == "__main__":
    unittest.main()
