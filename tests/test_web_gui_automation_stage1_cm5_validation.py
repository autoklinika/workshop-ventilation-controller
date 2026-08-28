from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_web_gui_automation_stage1_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_web_gui_automation_stage1_cm5.sh"
BRANCH = "agent/web-gui-automation-stage1"
MAIN_SHA = "7628c407cfc9c0ea72d262566759ea2d4598fec8"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("webgui_automation_validator", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WebGuiAutomationStage1Cm5ValidationTest(unittest.TestCase):
    def test_validator_is_valid_python(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        compile(source, str(VALIDATOR), "exec")

    def test_validator_accepts_only_shadow_command_boundary(self) -> None:
        validator = load_validator_module()
        safe = [
            {"command": "status"},
            {"command": "calendar"},
            {"command": "control-engine-operator"},
            {
                "command": "control-engine-operator-replace",
                "operator": {
                    "mode": "MANUAL",
                    "manual_supply_pct": 37.0,
                    "manual_extract_pct": 43.0,
                    "manual_aero_speed": 2,
                },
            },
            {
                "command": "control-engine-operator-replace",
                "operator": {"mode": "AUTO"},
            },
        ]
        validator._validate_command_boundary(safe)

        with self.assertRaisesRegex(validator.ValidationError, "SHADOW command boundary"):
            validator._validate_command_boundary(safe + [{"command": "set"}])

    def test_validator_rejects_actuating_or_nonzero_fixture_state(self) -> None:
        validator = load_validator_module()
        safe = {
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "shadow_automation": {
                "actuation_supported": False,
                "operator_mode": "AUTO",
            },
        }
        validator._require_non_actuating_state(safe, expected_operator_mode="AUTO")

        actuating = {
            **safe,
            "shadow_automation": {
                "actuation_supported": True,
                "operator_mode": "AUTO",
            },
        }
        with self.assertRaisesRegex(validator.ValidationError, "supports actuation"):
            validator._require_non_actuating_state(
                actuating, expected_operator_mode="AUTO"
            )

        nonzero = {
            **safe,
            "setpoints": {"supply_voltage": 1.0, "extract_voltage": 0.0},
        }
        with self.assertRaisesRegex(validator.ValidationError, "not 0 V"):
            validator._require_non_actuating_state(
                nonzero, expected_operator_mode="AUTO"
            )

    def test_harness_has_valid_bash_and_embedded_python_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        source = HARNESS.read_text(encoding="utf-8")
        marker = "<<'PY' &\n"
        self.assertEqual(source.count(marker), 1)
        embedded = source.split(marker, 1)[1].split("\nPY\nFAKE_PID=", 1)[0]
        compile(embedded, "<webgui-validation-fake-core>", "exec")

    def test_harness_pins_exact_remote_main_and_gui_branch(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn(f"BRANCH={BRANCH}", source)
        self.assertIn(f"EXPECTED_BASE={MAIN_SHA}", source)
        self.assertIn(
            'EXPECTED_BRANCH_SHA="${WEBGUI_AUTOMATION_EXPECTED_BRANCH_SHA:-}"',
            source,
        )
        self.assertIn(
            "WEBGUI_AUTOMATION_EXPECTED_BRANCH_SHA must pin the exact CI-tested branch commit",
            source,
        )
        self.assertIn("git ls-remote --exit-code origin refs/heads/main", source)
        self.assertIn('git ls-remote --exit-code origin "refs/heads/$BRANCH"', source)
        self.assertIn('git fetch --no-tags origin main "$BRANCH"', source)
        self.assertIn('[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ]', source)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', source)

    def test_harness_never_connects_staged_webgui_to_production_core(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('FAKE_SOCKET="$TEST_ROOT/fake-core.sock"', source)
        self.assertIn('WVC_CORE_SOCKET="$FAKE_SOCKET"', source)
        self.assertNotIn("/run/workshop-ventilation/ventilation-core.sock", source)
        self.assertIn("WEB_PORT=18093", source)
        self.assertIn("WVC_WEB_HOST=127.0.0.1", source)
        self.assertIn("validation-only fake core", source)

    def test_harness_has_no_production_restart_or_physical_control_path(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        forbidden = (
            "systemctl restart",
            "systemctl poweroff",
            "systemctl reboot",
            "sudo ",
            '"command": "set"',
            '"command": "stop"',
            '"command": "aero-speed"',
            '"command": "aero-airing"',
            "/api/v1/manual/fans",
            "/api/v1/manual/stop",
            "/api/v1/manual/aero",
            "--enable-scheduled-shutdown",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_harness_verifies_core_host_power_rtc_boot_and_main_are_unchanged(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('PROD_CORE_PID_AFTER="$(unit_pid "$CORE_UNIT")"', source)
        self.assertIn('[ "$PROD_CORE_PID_AFTER" = "$PROD_CORE_PID_BEFORE" ]', source)
        self.assertIn('[ "$(unit_cwd "$PROD_CORE_PID_AFTER")" = "$ROOT" ]', source)
        self.assertIn('[ "$(cat /proc/sys/kernel/random/boot_id)" = "$BOOT_ID_BEFORE" ]', source)
        self.assertIn('[ "$HOST_POWER_STATUS_AFTER" = "$HOST_POWER_STATUS_BEFORE" ]', source)
        self.assertIn('[ "$HOST_POWER_PID_AFTER" = "$HOST_POWER_PID_BEFORE" ]', source)
        self.assertIn('[ "$RTC_WAKE_AFTER" = "$RTC_WAKE_BEFORE" ]', source)
        self.assertIn('[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ]', source)
        self.assertIn('[ -z "$(git status --short)" ]', source)

    def test_validator_exercises_full_automation_surface_without_actuation(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        for endpoint in (
            '"/automation"',
            '"/api/v1/state"',
            '"/api/v1/calendar"',
            '"/api/v1/automation/operator"',
            '"/api/v1/automation/tuning-validation"',
        ):
            self.assertIn(endpoint, source)
        self.assertIn('"manual_supply_pct": 37.0', source)
        self.assertIn('"manual_extract_pct": 43.0', source)
        self.assertIn('"manual_aero_speed": 2', source)
        self.assertIn('"operator": {"mode": "AUTO"}', source)
        self.assertIn("default_runtime_binding", source)
        self.assertIn("ready_for_actuation_preconditions", source)


if __name__ == "__main__":
    unittest.main()
