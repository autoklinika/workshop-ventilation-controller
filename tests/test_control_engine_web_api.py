from __future__ import annotations

import unittest

from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.web.control_engine_app import ControlEngineWebApplication


class FakeCore:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.readback = {
            "revision": 1,
            "config": ControlEngineConfig().to_dict(),
            "actuation_supported": False,
        }

    def request(self, payload):
        self.requests.append(dict(payload))
        if payload.get("command") == "control-engine":
            return {"ok": True, "control_engine": self.readback}
        if payload.get("command") == "control-engine-replace":
            self.readback = {
                "revision": 2,
                "config": payload["config"],
                "actuation_supported": False,
                "dynamics_reset": True,
            }
            return {
                "ok": True,
                "control_engine": self.readback,
                "state": {"shadow_automation": {"actuation_supported": False}},
            }
        raise AssertionError(f"unexpected core request: {payload}")


class UnsafeCore(FakeCore):
    def request(self, payload):
        response = super().request(payload)
        if "control_engine" in response:
            response["control_engine"] = {
                **response["control_engine"],
                "actuation_supported": True,
            }
        return response


class ControlEngineWebApiTest(unittest.TestCase):
    def test_get_is_fixed_read_command(self) -> None:
        core = FakeCore()
        app = ControlEngineWebApplication(core)  # type: ignore[arg-type]
        response = app.handle("GET", "/api/v1/control-engine")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertFalse(response.payload["control_engine"]["actuation_supported"])
        self.assertEqual(core.requests, [{"command": "control-engine"}])

    def test_post_forwards_only_strict_full_config(self) -> None:
        core = FakeCore()
        app = ControlEngineWebApplication(core)  # type: ignore[arg-type]
        config = ControlEngineConfig().to_dict()
        response = app.handle(
            "POST",
            "/api/v1/control-engine",
            {"config": config},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests[0]["command"], "control-engine-replace")
        self.assertEqual(core.requests[0]["config"], config)
        self.assertFalse(response.payload["control_engine"]["actuation_supported"])

    def test_post_rejects_unknown_wrapper_field(self) -> None:
        core = FakeCore()
        app = ControlEngineWebApplication(core)  # type: ignore[arg-type]
        response = app.handle(
            "POST",
            "/api/v1/control-engine",
            {"config": ControlEngineConfig().to_dict(), "actuate": True},
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])

    def test_post_rejects_actuation_enable_inside_config(self) -> None:
        core = FakeCore()
        app = ControlEngineWebApplication(core)  # type: ignore[arg-type]
        config = ControlEngineConfig().to_dict()
        config["actuation_enabled"] = True
        response = app.handle("POST", "/api/v1/control-engine", {"config": config})
        self.assertEqual(response.status, 400)
        self.assertIn("unsupported fields", response.payload["error"])
        self.assertEqual(core.requests, [])

    def test_web_rejects_core_contract_claiming_actuation_support(self) -> None:
        app = ControlEngineWebApplication(UnsafeCore())  # type: ignore[arg-type]
        response = app.handle("GET", "/api/v1/control-engine")
        self.assertEqual(response.status, 502)
        self.assertFalse(response.payload["ok"])

    def test_other_paths_still_delegate_to_existing_web_application(self) -> None:
        core = FakeCore()
        app = ControlEngineWebApplication(core)  # type: ignore[arg-type]
        response = app.handle("GET", "/not-an-api")
        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
