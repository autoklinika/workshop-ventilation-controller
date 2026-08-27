import unittest

from ventilation_core.web.app import WebApplication


class FakeCoreClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return self.response


class WebCalendarApiTest(unittest.TestCase):
    def test_calendar_get_reads_authoritative_core_configuration(self):
        core = FakeCoreClient(
            {
                "ok": True,
                "calendar": {
                    "available": True,
                    "revision": 1,
                    "config": {
                        "schema_version": 1,
                        "timezone": "Europe/Warsaw",
                        "profiles": [],
                        "rules": [],
                    },
                    "state": {"available": True, "phase": "INACTIVE"},
                },
            }
        )
        response = WebApplication(core).handle("GET", "/api/v1/calendar")
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "calendar"}])

    def test_calendar_update_forwards_only_sanitized_configuration(self):
        core = FakeCoreClient({"ok": True, "calendar": {"available": True}})
        config = {
            "schema_version": 1,
            "timezone": "Europe/Warsaw",
            "profiles": [
                {
                    "profile_id": "WORK",
                    "mode": "AUTO",
                    "preventilation_minutes": 30,
                    "purge_minutes": 30,
                    "minimum_supply_pct": 25,
                    "minimum_extract_pct": 30,
                    "fixed_supply_pct": None,
                    "fixed_extract_pct": None,
                    "label": "Praca",
                }
            ],
            "rules": [
                {
                    "rule_id": "MON_FRI",
                    "kind": "WEEKLY",
                    "profile_id": "WORK",
                    "weekdays": [1, 2, 3, 4, 5],
                    "months": [],
                    "start_date": None,
                    "end_date": None,
                    "start_local": "07:00",
                    "end_local": "17:00",
                    "enabled": True,
                    "label": "Dni robocze",
                }
            ],
        }
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/calendar",
            {"config": config},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests,
            [{"command": "calendar-replace", "config": config}],
        )

    def test_calendar_update_rejects_unknown_top_level_field_before_core(self):
        core = FakeCoreClient({"ok": True})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/calendar",
            {
                "config": {
                    "schema_version": 1,
                    "timezone": "Europe/Warsaw",
                    "profiles": [],
                    "rules": [],
                    "command": "set",
                }
            },
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])

    def test_calendar_update_rejects_unknown_nested_fields_before_core(self):
        core = FakeCoreClient({"ok": True})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/calendar",
            {
                "config": {
                    "schema_version": 1,
                    "timezone": "Europe/Warsaw",
                    "profiles": [
                        {
                            "profile_id": "WORK",
                            "mode": "AUTO",
                            "supply_voltage": 10.0,
                        }
                    ],
                    "rules": [],
                }
            },
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])

    def test_calendar_update_requires_exact_config_envelope(self):
        core = FakeCoreClient({"ok": True})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/calendar",
            {"config": {}, "command": "set"},
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
