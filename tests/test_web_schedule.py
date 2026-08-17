import unittest

from ventilation_core.web.app import WebApplication


class FakeCoreClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return self.response


class WebScheduleApiTest(unittest.TestCase):
    def test_schedule_get_reads_authoritative_core_configuration(self):
        core = FakeCoreClient(
            {
                "ok": True,
                "schedule": {
                    "available": True,
                    "timezone": "Europe/Warsaw",
                    "windows": [],
                },
            }
        )
        response = WebApplication(core).handle("GET", "/api/v1/schedule")
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "schedule"}])

    def test_schedule_zone_update_forwards_only_sanitized_configuration(self):
        core = FakeCoreClient({"ok": True, "schedule": {"available": True}})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/schedule/zone",
            {
                "zone": "zone-1",
                "windows": [
                    {
                        "weekday": 1,
                        "start_local": "07:00",
                        "end_local": "15:00",
                        "expectation": "OCCUPIED_EXPECTED",
                        "enabled": True,
                        "label": "Zmiana 1",
                    }
                ],
            },
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests,
            [
                {
                    "command": "schedule-replace",
                    "zone": "zone-1",
                    "windows": [
                        {
                            "weekday": 1,
                            "start_local": "07:00",
                            "end_local": "15:00",
                            "expectation": "OCCUPIED_EXPECTED",
                            "enabled": True,
                            "label": "Zmiana 1",
                        }
                    ],
                }
            ],
        )

    def test_schedule_update_rejects_unknown_zone_before_core(self):
        core = FakeCoreClient({"ok": True})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/schedule/zone",
            {"zone": "other", "windows": []},
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])

    def test_schedule_update_rejects_unknown_fields_before_core(self):
        core = FakeCoreClient({"ok": True})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/schedule/zone",
            {
                "zone": "zone-1",
                "windows": [
                    {
                        "weekday": 1,
                        "start_local": "07:00",
                        "end_local": "15:00",
                        "command": "set",
                    }
                ],
            },
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])

    def test_schedule_update_rejects_unknown_expectation(self):
        core = FakeCoreClient({"ok": True})
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/schedule/zone",
            {
                "zone": "zone-2",
                "windows": [
                    {
                        "weekday": 5,
                        "start_local": "08:00",
                        "end_local": "16:00",
                        "expectation": "BOOST",
                    }
                ],
            },
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
