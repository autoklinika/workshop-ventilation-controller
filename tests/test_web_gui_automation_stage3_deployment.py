from __future__ import annotations

import unittest
from pathlib import Path

from ventilation_core.runtime.control_engine_server import ControlEngineCoreServer
from ventilation_core.web.main import DEFAULT_PORT


ROOT = Path(__file__).resolve().parents[1]


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
                    "operator": {"mode": "MANUAL", "manual_supply_pct": 20.0, "manual_extract_pct": 20.0, "manual_aero_speed": 1},
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
        self.assertNotIn("actuation-enable", app)
        self.assertNotIn("actuation_enabled", app)


if __name__ == "__main__":
    unittest.main()
