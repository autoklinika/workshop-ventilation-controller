from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest

from ventilation_core.web.control_engine_app import ControlEngineWebApplication


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_web_gui_automation_stage2_runtime_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_web_gui_automation_stage2_runtime_cm5.sh"
WEB_APP = ROOT / "src" / "ventilation_core" / "web" / "control_engine_app.py"
CORE_SERVER = ROOT / "src" / "ventilation_core" / "runtime" / "control_engine_server.py"
BRANCH = "agent/web-gui-automation-stage2-runtime"
MAIN_SHA = "7628c407cfc9c0ea72d262566759ea2d4598fec8"


class FakeCoreClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return self.responses.pop(0)


def _load_validator():
    spec = importlib.util.spec_from_file_location("webgui_automation_stage2_validator", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RealCoreOperatorProjectionTest(unittest.TestCase):
    def test_web_api_normalizes_authoritative_core_operator_field(self) -> None:
        operator = {
            "revision": 0,
            "intent": {
                "mode": "AUTO",
                "manual_supply_pct": None,
                "manual_extract_pct": None,
                "manual_aero_speed": None,
            },
            "persistent": False,
            "reset_on_core_restart": True,
            "actuation_supported": False,
        }
        core = FakeCoreClient([{"ok": True, "operator": operator}])
        response = ControlEngineWebApplication(core).handle(
            "GET", "/api/v1/automation/operator"
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.payload,
            {"ok": True, "control_engine_operator": operator},
        )
        self.assertEqual(core.requests, [{"command": "control-engine-operator"}])

    def test_web_api_rejects_missing_real_core_operator_object(self) -> None:
        core = FakeCoreClient([{"ok": True, "operator": None}])
        response = ControlEngineWebApplication(core).handle(
            "GET", "/api/v1/automation/operator"
        )
        self.assertEqual(response.status, 502)
        self.assertEqual(core.requests, [{"command": "control-engine-operator"}])

    def test_core_and_web_projection_contract_are_explicit_in_source(self) -> None:
        core_source = CORE_SERVER.read_text(encoding="utf-8")
        web_source = WEB_APP.read_text(encoding="utf-8")
        self.assertIn('return {"ok": True, "operator": operator}', core_source)
        self.assertIn('operator = response.get("operator")', web_source)
        self.assertIn('"control_engine_operator": operator', web_source)


class Stage2ValidatorContractTest(unittest.TestCase):
    def test_validator_is_valid_python(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        compile(source, str(VALIDATOR), "exec")
        module = _load_validator()
        safe_auto = {
            "revision": 0,
            "intent": {
                "mode": "AUTO",
                "manual_supply_pct": None,
                "manual_extract_pct": None,
                "manual_aero_speed": None,
            },
            "persistent": False,
        }
        module._require_auto_operator(safe_auto, label="test")

        stale = {
            "revision": 0,
            "intent": {
                "mode": "AUTO",
                "manual_supply_pct": 20.0,
                "manual_extract_pct": None,
                "manual_aero_speed": None,
            },
            "persistent": False,
        }
        with self.assertRaisesRegex(module.ValidationError, "stale manual_supply_pct"):
            module._require_auto_operator(stale, label="test")

    def test_validator_uses_only_shadow_calendar_and_readonly_paths(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('"/api/v1/state"', source)
        self.assertIn('"/api/v1/calendar"', source)
        self.assertIn('"/api/v1/automation/operator"', source)
        self.assertIn('"/api/v1/automation/tuning-validation"', source)
        for forbidden in (
            "/api/v1/manual/fans",
            "/api/v1/manual/stop",
            "/api/v1/manual/aero",
            "/api/v1/host-power",
            "/api/v1/automation/command",
        ):
            self.assertNotIn(forbidden, source)

    def test_validator_requires_zero_volts_no_motion_and_no_authority(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('setpoints.get("supply_voltage") != 0.0', source)
        self.assertIn('setpoints.get("extract_voltage") != 0.0', source)
        self.assertIn('shadow.get("actuation_supported") is not False', source)
        self.assertIn('readiness.get("actuation_authorized") is not False', source)
        self.assertIn('readiness.get("ready") is not False', source)
        self.assertIn('tacho_failure_confirmation_seconds', source)
        self.assertIn('abs(float(confirmation) - 4.0)', source)

    def test_validator_exercises_calendar_persistence_and_volatile_operator_reset(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('payload={"config": calendar_config}', source)
        self.assertIn('revision_before + 1', source)
        self.assertIn('"manual_supply_pct": 37.0', source)
        self.assertIn('payload={"mode": "AUTO"}', source)
        self.assertIn('operator.get("revision") != 0', source)
        self.assertIn('Calendar configuration did not persist across real core restart', source)


class Stage2HarnessContractTest(unittest.TestCase):
    def test_harness_has_valid_bash_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_harness_pins_main_and_exact_stage2_branch(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn(f"BRANCH={BRANCH}", source)
        self.assertIn(f"EXPECTED_MAIN={MAIN_SHA}", source)
        self.assertIn('EXPECTED_BRANCH_SHA="${WEBGUI_AUTOMATION_STAGE2_EXPECTED_BRANCH_SHA:-}"', source)
        self.assertIn('git fetch --no-tags origin main "$BRANCH"', source)
        self.assertIn('BRANCH_LS_REMOTE="$(git ls-remote origin "refs/heads/$BRANCH"', source)
        self.assertIn('[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ]', source)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', source)

    def test_harness_uses_real_branch_core_socket_but_isolated_automation_db(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock", source)
        self.assertIn("--automation-db $TEST_ROOT/automation.sqlite3", source)
        self.assertIn("WorkingDirectory=$WT", source)
        self.assertIn("Environment=PYTHONPATH=$WT/src", source)
        self.assertIn("WEB_PORT=18094", source)
        self.assertNotIn("web_gui_automation_fake_core.py", source)
        self.assertNotIn("validation-only fake core", source.lower())

    def test_harness_never_enables_scheduled_shutdown_or_host_power_actions(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('case "$execstart" in', source)
        self.assertIn('*--enable-scheduled-shutdown*) fail', source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("systemctl --no-block poweroff", source)
        self.assertNotIn("systemctl --no-block reboot", source)
        self.assertNotIn('"command": "shutdown"', source)

    def test_harness_does_not_issue_physical_control_commands(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertNotIn("ctl \"$WT/src\" set", source)
        self.assertNotIn("ctl \"$WT/src\" stop", source)
        self.assertNotIn("aero-speed", source)
        self.assertNotIn("aero-airing", source)
        self.assertNotIn("ventilation_core.ctl set", source)
        self.assertNotIn("ventilation_core.ctl stop", source)

    def test_harness_snapshots_both_production_automation_rows_and_rolls_back(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('("calendar_configuration", "control_engine_configuration")', source)
        self.assertIn("PRODUCTION_AUTOMATION_ROWS_BEFORE", source)
        self.assertIn("production Calendar/Control Engine SQLite rows unchanged", source)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', source)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', source)
        self.assertIn('require_zero_output "$ROOT/src" "rollback production main" 0', source)
        self.assertIn('assert_host_untouched "rollback production main"', source)


if __name__ == "__main__":
    unittest.main()
