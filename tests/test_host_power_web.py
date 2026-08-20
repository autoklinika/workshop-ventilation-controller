from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.web.alert_history_app import AlertHistoryWebApplication
from ventilation_core.web.host_power import HostPowerError


ROOT = Path(__file__).resolve().parents[1]


class FakeCore:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        self.requests.append(dict(payload))
        return {"ok": True}


class FakeHostPower:
    def __init__(self) -> None:
        self.actions: list[str] = []
        self.error: Exception | None = None

    def request(self, action: str) -> dict[str, object]:
        self.actions.append(action)
        if self.error is not None:
            raise self.error
        return {"ok": True, "accepted": True, "action": action}


class HostPowerWebTest(unittest.TestCase):
    def test_explicit_shutdown_and_restart_are_forwarded_only_to_host_power_agent(self) -> None:
        core = FakeCore()
        power = FakeHostPower()
        app = AlertHistoryWebApplication(core, host_power=power)

        shutdown = app.handle(
            "POST",
            "/api/v1/system/power",
            {"action": "shutdown"},
        )
        restart = app.handle(
            "POST",
            "/api/v1/system/power",
            {"action": "restart"},
        )

        self.assertEqual(shutdown.status, 202)
        self.assertEqual(shutdown.payload, {"ok": True, "accepted": True, "action": "shutdown"})
        self.assertEqual(restart.status, 202)
        self.assertEqual(restart.payload, {"ok": True, "accepted": True, "action": "restart"})
        self.assertEqual(power.actions, ["shutdown", "restart"])
        self.assertEqual(core.requests, [])

    def test_host_power_endpoint_rejects_generic_or_malformed_commands(self) -> None:
        power = FakeHostPower()
        app = AlertHistoryWebApplication(FakeCore(), host_power=power)

        cases = (
            None,
            {},
            {"action": "halt"},
            {"action": "restart", "command": "anything"},
            {"command": "reboot"},
        )
        for body in cases:
            with self.subTest(body=body):
                response = app.handle("POST", "/api/v1/system/power", body)
                self.assertEqual(response.status, 400)

        self.assertEqual(power.actions, [])
        self.assertEqual(app.handle("GET", "/api/v1/system/power").status, 404)
        self.assertEqual(app.handle("POST", "/api/v1/system/command", {"action": "restart"}).status, 404)

    def test_agent_unavailable_is_reported_without_falling_back_to_core_or_shell(self) -> None:
        core = FakeCore()
        power = FakeHostPower()
        power.error = HostPowerError("socket unavailable")
        app = AlertHistoryWebApplication(core, host_power=power)

        response = app.handle("POST", "/api/v1/system/power", {"action": "restart"})

        self.assertEqual(response.status, 503)
        self.assertFalse(response.payload["ok"])
        self.assertIn("socket unavailable", response.payload["error"])
        self.assertEqual(core.requests, [])

    def test_web_main_wires_only_unix_host_power_client(self) -> None:
        main = (ROOT / "src" / "ventilation_core" / "web" / "main.py").read_text(encoding="utf-8")
        self.assertIn("HostPowerClient", main)
        self.assertIn("WVC_HOST_POWER_SOCKET", main)
        self.assertIn("host_power=host_power", main)
        self.assertNotIn("systemctl", main)
        self.assertNotIn("subprocess", main)


if __name__ == "__main__":
    unittest.main()
