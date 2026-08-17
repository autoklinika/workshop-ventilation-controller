from __future__ import annotations

import unittest

from ventilation_core.telemetry.history import TelemetryHistoryStatus
from ventilation_core.web.app import WebApplication


class FakeCoreClient:
    def __init__(self) -> None:
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "state": {"mode": "STOP"}}


class FakeHistory:
    def __init__(self) -> None:
        self.queries = []

    def status(self):
        return TelemetryHistoryStatus(
            available=True,
            total_samples=10,
            pending_samples=2,
            synced_samples=8,
            oldest_captured_at="2026-08-17T10:00:00+00:00",
            newest_captured_at="2026-08-17T10:00:45+00:00",
            oldest_pending_at="2026-08-17T10:00:40+00:00",
            last_synced_at="2026-08-17T10:00:42+00:00",
        )

    def query(self, *, start_at=None, end_at=None, limit=720):
        self.queries.append((start_at, end_at, limit))
        return [
            {
                "sequence": 10,
                "sample_id": "sample-10",
                "captured_at": "2026-08-17T10:00:45+00:00",
                "synced": False,
                "metrics": {"mode": "STOP"},
            }
        ]


class WebHistoryTest(unittest.TestCase):
    def test_history_status_does_not_call_core(self) -> None:
        core = FakeCoreClient()
        history = FakeHistory()
        response = WebApplication(core, history=history).handle("GET", "/api/v1/history/status")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["history"]["available"])
        self.assertTrue(response.payload["history"]["configured"])
        self.assertEqual(response.payload["history"]["pending_samples"], 2)
        self.assertEqual(core.requests, [])

    def test_history_query_is_read_only_and_forwards_only_query_fields(self) -> None:
        core = FakeCoreClient()
        history = FakeHistory()
        response = WebApplication(core, history=history).handle(
            "POST",
            "/api/v1/history/query",
            {
                "start_at": "2026-08-17T10:00:00+00:00",
                "end_at": "2026-08-17T11:00:00+00:00",
                "limit": 100,
            },
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["count"], 1)
        self.assertEqual(
            history.queries,
            [("2026-08-17T10:00:00+00:00", "2026-08-17T11:00:00+00:00", 100)],
        )
        self.assertEqual(core.requests, [])

    def test_history_is_explicitly_unavailable_when_not_configured(self) -> None:
        core = FakeCoreClient()
        app = WebApplication(core)
        status = app.handle("GET", "/api/v1/history/status")
        query = app.handle("POST", "/api/v1/history/query", {})
        self.assertEqual(status.status, 200)
        self.assertFalse(status.payload["history"]["available"])
        self.assertFalse(status.payload["history"]["configured"])
        self.assertEqual(query.status, 503)
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
