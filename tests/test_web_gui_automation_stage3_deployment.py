from __future__ import annotations

import ast
import shutil
import subprocess
import unittest
from pathlib import Path

from ventilation_core.runtime.control_engine_server import ControlEngineCoreServer
from ventilation_core.web.main import DEFAULT_PORT


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_web_gui_automation_stage3_deployment_cm5.sh"
VALIDATOR = ROOT / "tools" / "validate_web_gui_automation_stage3_deployment_cm5.py"


class _State:
    def __init__(self, *, supported: bool = False, authorized: bool = False, ready: bool = False):
        self.supported = supported
        self.authorized = authorized
        self.ready = ready

    def to_dict(self):
        return {
            "shadow_automation": {
                "actuation_supported": self.supported,
                "actuation_readiness": {
                    "actuation_authorized": self.authorized,
                    "ready": self.ready,
                },
            }
        }


class _Service:
    def __init__(self, *, supported: bool = False, authorized: bool = False, ready: bool = False):
        self.supported = supported
        self.authorized = authorized
        self.ready = ready
        self.replacements = []

    def control_engine_configuration(self):
        return {
            "revision": 1,
            "config": {},
            "actuation_supported": self.supported,
        }

    def state(self):
        return _State(
            supported=self.supported,
            authorized=self.authorized,
            ready=self.ready,
        )

    def replace_control_engine_operator_intent(self, intent):
        self.replacements.append(dict(intent))
        return {
            "revision": len(self.replacements),
            "persistent": False,
            "intent": dict(intent),
            "actuation_supported": self.supported,
        }


class Stage3ShadowOnlyCoreGuardTest(unittest.IsolatedAsyncioTestCase):
    def _server(self, service: _Service) -> ControlEngineCoreServer:
        server = object.__new__(ControlEngineCoreServer)
        server._service = service
        return server

    async def test_shadow_only_web_client_request_is_accepted_while_core_is_fail_closed(self):
        service = _Service()
        response = await self._server(service)._dispatch(
            {
                "command": "control-engine-operator-replace",
                "operator": {"mode": "AUTO"},
                "require_shadow_only": True,
            }
        )
        self.assertTrue(response["ok"])
        self.assertEqual(service.replacements, [{"mode": "AUTO"}])

    async def test_shadow_only_web_client_request_is_rejected_if_core_supports_actuation(self):
        service = _Service(supported=True)
        with self.assertRaisesRegex(RuntimeError, "supports actuation"):
            await self._server(service)._dispatch(
                {
                    "command": "control-engine-operator-replace",
                    "operator": {
                        "mode": "MANUAL",
                        "manual_supply_pct": 20.0,
                        "manual_extract_pct": 20.0,
                        "manual_aero_speed": 1,
                    },
                    "require_shadow_only": True,
                }
            )
        self.assertEqual(service.replacements, [])

    async def test_shadow_only_web_client_request_is_rejected_if_authority_or_readiness_appears(self):
        for authorized, ready in ((True, False), (False, True)):
            with self.subTest(authorized=authorized, ready=ready):
                service = _Service(authorized=authorized, ready=ready)
                with self.assertRaisesRegex(RuntimeError, "not fail-closed"):
                    await self._server(service)._dispatch(
                        {
                            "command": "control-engine-operator-replace",
                            "operator": {"mode": "AUTO"},
                            "require_shadow_only": True,
                        }
                    )
                self.assertEqual(service.replacements, [])

    async def test_shadow_only_flag_must_be_boolean(self):
        service = _Service()
        with self.assertRaisesRegex(ValueError, "require_shadow_only must be a boolean"):
            await self._server(service)._dispatch(
                {
                    "command": "control-engine-operator-replace",
                    "operator": {"mode": "AUTO"},
                    "require_shadow_only": "yes",
                }
            )
        self.assertEqual(service.replacements, [])


class Stage3WebClientContractTest(unittest.TestCase):
    def test_default_webgui_port_is_18091(self):
        self.assertEqual(DEFAULT_PORT, 18091)
        env = (ROOT / "deploy/cm5/web/wvc-web-ui.env.example").read_text(encoding="utf-8")
        self.assertIn("WVC_WEB_PORT=18091", env)
        self.assertNotIn("WVC_WEB_PORT=8088", env)

    def test_webgui_remains_independent_client_without_actuation_enable_surface(self):
        unit = (ROOT / "deploy/systemd/wvc-web-ui.service").read_text(encoding="utf-8")
        app = (ROOT / "src/ventilation_core/web/control_engine_app.py").read_text(encoding="utf-8")
        self.assertNotIn("Requires=ventilation-core.service", unit)
        self.assertIn('"require_shadow_only": True', app)
        self.assertNotIn('"/api/v1/actuation-enable"', app)
        self.assertNotIn('"/api/v1/automation/actuation-enable"', app)
        self.assertNotIn('"actuation_enabled":', app)


class Stage3SystemdHarnessContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = HARNESS.read_text(encoding="utf-8")
        cls.validator = VALIDATOR.read_text(encoding="utf-8")

    def test_harness_has_valid_bash_syntax(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        subprocess.run([bash, "-n", str(HARNESS)], check=True)

    def test_validator_is_valid_python(self):
        ast.parse(self.validator)
        self.assertIn("import validate_web_gui_automation_stage2_runtime_cm5 as stage2", self.validator)

    def test_harness_pins_main_exact_stage3_branch_and_port_18091(self):
        self.assertIn("EXPECTED_MAIN=7628c407cfc9c0ea72d262566759ea2d4598fec8", self.harness)
        self.assertIn("BRANCH=agent/web-gui-automation-stage3-deployment", self.harness)
        self.assertIn("WEBGUI_AUTOMATION_STAGE3_EXPECTED_BRANCH_SHA", self.harness)
        self.assertIn("WEB_PORT=18091", self.harness)
        self.assertNotIn("WEB_PORT=18094", self.harness)
        self.assertNotIn("WEB_PORT=8088", self.harness)
        self.assertIn("git ls-remote origin refs/heads/main", self.harness)
        self.assertIn('git ls-remote origin "refs/heads/$BRANCH"', self.harness)

    def test_harness_uses_real_systemd_webgui_client_not_foreground_web_process(self):
        self.assertIn("WEB_UNIT=wvc-web-ui.service", self.harness)
        self.assertIn('sudo systemctl restart "$WEB_UNIT"', self.harness)
        self.assertIn('assert_branch_web_runtime "Stage3 WebGUI startup"', self.harness)
        self.assertIn("WorkingDirectory=$WT", self.harness)
        self.assertIn("Environment=WVC_WEB_PORT=$WEB_PORT", self.harness)
        self.assertIn("Environment=WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock", self.harness)
        self.assertIn("EnvironmentFile=", self.harness)
        self.assertNotIn("/usr/bin/python3 -B -m ventilation_core.web.main >", self.harness)
        self.assertNotIn("WEB_PID=$!", self.harness)

    def test_webgui_restart_proves_client_state_is_core_owned(self):
        self.assertIn("CORE_PID_BEFORE_WEB_RESTART", self.harness)
        self.assertIn("--phase web-restart", self.harness)
        self.assertIn("WebGUI restart unexpectedly restarted authoritative core", self.harness)
        self.assertIn("operator_revision_before_restart", self.validator)
        self.assertIn("WebGUI restart changed core-owned Calendar revision", self.validator)

    def test_core_restart_proves_independent_client_survives(self):
        self.assertIn("WEB_PID_BEFORE_CORE_RESTART", self.harness)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.harness)
        self.assertIn("--phase core-restart", self.harness)
        self.assertIn("core restart unexpectedly restarted independent WebGUI client", self.harness)
        self.assertIn("stage2.verify(web_url, state_file)", self.validator)

    def test_harness_uses_isolated_automation_db_and_keeps_production_rows_unchanged(self):
        self.assertIn("TEST_ROOT=/var/tmp/wvc-webgui-automation-stage3-deployment", self.harness)
        self.assertIn("--automation-db $TEST_ROOT/automation.sqlite3", self.harness)
        self.assertIn("PRODUCTION_AUTOMATION_ROWS_BEFORE", self.harness)
        self.assertIn("production Calendar/Control Engine SQLite rows unchanged by isolated Stage3", self.harness)

    def test_harness_does_not_issue_physical_control_or_host_power_actions(self):
        forbidden = (
            'ctl "$WT/src" set',
            'ctl "$WT/src" stop',
            'ctl "$WT/src" aero-speed',
            'ctl "$WT/src" aero-airing',
            "systemctl poweroff",
            "systemctl reboot",
            "/sbin/shutdown",
            "/sbin/reboot",
            '"action":"shutdown"',
            '"action":"restart"',
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.harness)
        self.assertIn("--enable-scheduled-shutdown", self.harness)
        self.assertIn("scheduled shutdown unexpectedly enabled", self.harness)

    def test_harness_restores_webgui_state_core_host_rtc_and_main(self):
        for marker in (
            "WEB_ACTIVE_BEFORE",
            "WEB_ENABLED_BEFORE",
            "WEB_PORT_BEFORE",
            'sudo rm -f "$WEB_DROPIN" "$CORE_DROPIN"',
            'assert_host_untouched "rollback production main"',
            "production main remains clean at $EXPECTED_MAIN",
            "production $WEB_UNIT restored",
        ):
            self.assertIn(marker, self.harness)


if __name__ == "__main__":
    unittest.main()
