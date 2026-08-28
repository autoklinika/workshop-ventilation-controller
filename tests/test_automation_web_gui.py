import json
import unittest
from pathlib import Path

from ventilation_core.web.control_engine_app import ControlEngineWebApplication


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class FakeCoreClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        if self.responses:
            return self.responses.pop(0)
        return {"ok": True}


class AutomationWebApiTest(unittest.TestCase):
    def test_operator_get_uses_only_fixed_read_command(self):
        core = FakeCoreClient([
            {
                "ok": True,
                "control_engine_operator": {
                    "revision": 0,
                    "persistent": False,
                    "intent": {"mode": "AUTO"},
                },
            }
        ])
        response = ControlEngineWebApplication(core).handle(
            "GET", "/api/v1/automation/operator"
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "control-engine-operator"}])

    def test_operator_auto_replace_forwards_only_validated_operator_intent(self):
        core = FakeCoreClient([{"ok": True, "control_engine_operator": {}}])
        response = ControlEngineWebApplication(core).handle(
            "POST", "/api/v1/automation/operator", {"mode": "AUTO"}
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests,
            [
                {
                    "command": "control-engine-operator-replace",
                    "operator": {"mode": "AUTO"},
                }
            ],
        )

    def test_operator_manual_replace_forwards_exact_validated_shadow_intent(self):
        core = FakeCoreClient([{"ok": True, "control_engine_operator": {}}])
        intent = {
            "mode": "MANUAL",
            "manual_supply_pct": 37.0,
            "manual_extract_pct": 43.0,
            "manual_aero_speed": 2,
        }
        response = ControlEngineWebApplication(core).handle(
            "POST", "/api/v1/automation/operator", intent
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests,
            [
                {
                    "command": "control-engine-operator-replace",
                    "operator": intent,
                }
            ],
        )

    def test_operator_invalid_manual_intent_is_rejected_before_core(self):
        invalid_intents = (
            {
                "mode": "MANUAL",
                "manual_supply_pct": True,
                "manual_extract_pct": 20,
                "manual_aero_speed": 1,
            },
            {
                "mode": "MANUAL",
                "manual_supply_pct": 20,
                "manual_extract_pct": 20,
            },
            {"mode": "AUTO", "manual_supply_pct": 20},
            {"mode": "MANUAL", "manual_supply_pct": 101, "manual_extract_pct": 20, "manual_aero_speed": 1},
            {"mode": "MANUAL", "manual_supply_pct": 20, "manual_extract_pct": 20, "manual_aero_speed": 4},
            {"mode": "AUTO", "command": "set"},
        )
        for intent in invalid_intents:
            with self.subTest(intent=intent):
                core = FakeCoreClient()
                response = ControlEngineWebApplication(core).handle(
                    "POST", "/api/v1/automation/operator", intent
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(core.requests, [])

    def test_tuning_validation_is_read_only_and_reports_one_of_nine_complete(self):
        core = FakeCoreClient()
        app = ControlEngineWebApplication(core)
        response = app.handle("GET", "/api/v1/automation/tuning-validation")
        self.assertEqual(response.status, 200)
        ledger = response.payload["tuning_validation"]
        self.assertEqual(ledger["completed"], 1)
        self.assertEqual(ledger["total"], 9)
        self.assertFalse(ledger["default_runtime_binding"])
        satisfied = [group["id"] for group in ledger["groups"] if group["satisfied"]]
        self.assertEqual(satisfied, ["tacho_confirmation"])
        self.assertEqual(core.requests, [])

        blocked = app.handle(
            "POST", "/api/v1/automation/tuning-validation", {"groups": {}}
        )
        self.assertEqual(blocked.status, 405)
        self.assertEqual(core.requests, [])

    def test_no_generic_automation_command_proxy_exists(self):
        core = FakeCoreClient()
        response = ControlEngineWebApplication(core).handle(
            "POST", "/api/v1/automation/command", {"command": "set"}
        )
        self.assertEqual(response.status, 404)
        self.assertEqual(core.requests, [])


class AutomationStaticContractTest(unittest.TestCase):
    def setUp(self):
        self.html = (STATIC / "automation.html").read_text(encoding="utf-8")
        self.js = (STATIC / "automation.js").read_text(encoding="utf-8")
        self.index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.server = (
            ROOT / "src" / "ventilation_core" / "web" / "server.py"
        ).read_text(encoding="utf-8")

    def test_main_sidebar_exposes_automation_and_server_routes_it(self):
        self.assertIn('href="/automation"', self.index)
        self.assertIn(">AUTOMATYKA<", self.index)
        self.assertIn('request_path in ("/automation", "/automation/")', self.server)
        self.assertIn('relative = "automation.html"', self.server)
        for asset in ("automation.html", "automation.css", "automation.js"):
            self.assertIn(f'"{asset}"', self.server)

    def test_automation_page_has_four_tabs_and_permanent_shadow_warning(self):
        self.assertIn("SHADOW — BRAK STEROWANIA FIZYCZNYMI WYJŚCIAMI", self.html)
        for tab in ("state", "schedule", "manual", "tuning"):
            self.assertIn(f'data-automation-tab="{tab}"', self.html)
            self.assertIn(f'data-automation-panel="{tab}"', self.html)
        self.assertIn("TRYB TESTOWY / SHADOW", self.html)
        self.assertIn("Nie steruje", self.html)

    def test_schedule_reuses_existing_calendar_contract(self):
        required_ids = (
            "calendarAvailability",
            "calendarError",
            "calendarRevision",
            "calendarTimezoneState",
            "calendarPhase",
            "calendarMode",
            "calendarProfile",
            "calendarRuleSource",
            "calendarRuleId",
            "calendarNextTransition",
            "calendarNextWake",
            "calendarLocalTime",
            "calendarTimezone",
            "calendarProfilesRows",
            "calendarProfilesEmpty",
            "calendarRulesRows",
            "calendarRulesEmpty",
            "calendarMessage",
        )
        for element_id in required_ids:
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn('data-calendar-editor', self.html)
        self.assertIn('src="/calendar.js"', self.html)
        self.assertIn('href="/calendar.css"', self.html)
        self.assertIn("Nie jest harmonogramem zasilania CM5", self.html)

    def test_automation_browser_uses_only_shadow_state_operator_and_readonly_ledger(self):
        allowed_api_literals = {
            "/api/v1/state",
            "/api/v1/automation/operator",
            "/api/v1/automation/tuning-validation",
        }
        discovered = set()
        marker = '"/api/v1/'
        start = 0
        while True:
            pos = self.js.find(marker, start)
            if pos < 0:
                break
            end = self.js.find('"', pos + 1)
            discovered.add(self.js[pos + 1:end])
            start = end + 1
        self.assertEqual(discovered, allowed_api_literals)

        forbidden = (
            "/api/v1/manual/fans",
            "/api/v1/manual/stop",
            "/api/v1/manual/aero",
            "/api/v1/host-power",
            "control-engine-replace",
            "scheduled-shutdown",
            "aero-speed",
            "aero-airing",
        )
        for token in forbidden:
            self.assertNotIn(token, self.js)

    def test_tuning_source_profile_is_still_one_of_nine_and_unbound(self):
        ledger = json.loads(
            (ROOT / "config" / "control-engine-tuning-validation-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(ledger["default_runtime_binding"])
        groups = ledger["groups"]
        self.assertEqual(len(groups), 9)
        self.assertEqual(groups["tacho_confirmation"]["current_level"], "PHYSICAL_VALIDATED")
        for group_id, group in groups.items():
            if group_id == "tacho_confirmation":
                continue
            self.assertNotEqual(group["current_level"], "WORKSHOP_VALIDATED")


if __name__ == "__main__":
    unittest.main()
