import re
import unittest
from pathlib import Path

from ventilation_core.web.app import WebApplication


ROOT = Path(__file__).resolve().parents[1]


class FakeCoreClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return self.response


class WebTachoContractTest(unittest.TestCase):
    def test_state_passes_optional_tacho_contract_through_verbatim(self):
        tacho = {
            "chip_path": "/dev/gpiochip0",
            "ready": True,
            "worker_alive": True,
            "last_error": None,
            "supply": None,
            "extract": {
                "line_name": "GPIO27",
                "line_offset": 27,
                "frequency_hz": 65.1,
                "rpm": 1302.0,
                "sample_count": 6,
                "age_seconds": 0.01,
                "valid": True,
            },
        }
        core = FakeCoreClient({"ok": True, "state": {"mode": "MANUAL", "tacho": tacho}})

        response = WebApplication(core).handle("GET", "/api/v1/state")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["state"]["tacho"], tacho)
        self.assertEqual(core.requests, [{"command": "status"}])

    def test_dashboard_distinguishes_command_voltage_rpm_and_tacho_state(self):
        html = (ROOT / "src/ventilation_core/web/static/index.html").read_text(encoding="utf-8")
        for element_id in (
            "supplyCommandPercent",
            "supplyActual",
            "supplyRpm",
            "supplyTachoChip",
            "extractCommandPercent",
            "extractActual",
            "extractRpm",
            "extractTachoChip",
            "tachoHealth",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('src="/tacho.js"', html)

    def test_invalid_tacho_is_not_presented_as_confirmed_zero_rpm(self):
        js = (ROOT / "src/ventilation_core/web/static/tacho.js").read_text(encoding="utf-8")
        self.assertIn('rpmElement.textContent = "—"', js)
        self.assertIn('channel.valid === true', js)
        self.assertIn('TACHO: brak sygnału', js)
        self.assertIn('TACHO: nie skonfigurowano', js)
        self.assertIn('TACHO: błąd monitora', js)
        self.assertNotIn('expected_rpm', js)
        self.assertNotIn('under-speed', js)
        self.assertNotIn('over-speed', js)

    def test_tacho_renderer_is_read_only_and_does_not_gate_manual_control(self):
        tacho_js = (ROOT / "src/ventilation_core/web/static/tacho.js").read_text(encoding="utf-8")
        app_js = (ROOT / "src/ventilation_core/web/static/app.js").read_text(encoding="utf-8")

        self.assertIn('fetch("/api/v1/state"', tacho_js)
        self.assertNotIn('/api/v1/manual/', tacho_js)
        self.assertNotIn('method: "POST"', tacho_js)

        match = re.search(r"const fanDisabled = ([^;]+);", app_js)
        self.assertIsNotNone(match)
        self.assertNotIn("tacho", match.group(1).lower())

    def test_http_static_whitelist_includes_tacho_script(self):
        server = (ROOT / "src/ventilation_core/web/server.py").read_text(encoding="utf-8")
        self.assertIn('"tacho.js"', server)


if __name__ == "__main__":
    unittest.main()
