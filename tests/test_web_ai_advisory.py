import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ventilation_core.web.advisory import AdvisoryError, FileAdvisoryProvider
from ventilation_core.web.app import WebApplication


SOURCE_ID = "workshop-ventilation-cm5-01"


def valid_report(window_end: str = "2026-08-19T12:30:00Z"):
    return {
        "delivery_schema_version": 1,
        "analysis_id": "test-analysis-id",
        "source_id": SOURCE_ID,
        "advisory_only": True,
        "experimental": True,
        "control_actions_supported": False,
        "window_start": "2026-08-19T12:15:00Z",
        "window_end": window_end,
        "created_at": "2026-08-19T12:30:30Z",
        "sample_count": 180,
        "model": "qwen3.6:35b",
        "prompt_version": "ventilation-v12.2-adverse-trend-gate",
        "result": {
            "schema_version": 2,
            "status": "no_anomaly_detected",
            "analysis_pl": "Brak dodatkowych faktów wymagających wyróżnienia.",
            "operator_recommendation_pl": "Brak dodatkowych zaleceń.",
            "data_quality_pl": "Dane kompletne.",
        },
    }


class FakeCore:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "state": {"mode": "STOP"}}


class StaticAdvisoryProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_snapshot(self):
        return self.snapshot


class WebAiAdvisoryTest(unittest.TestCase):
    def _write_cache(self, root: Path, report: dict):
        path = root / "ai-advisory.json"
        path.write_text(
            json.dumps(
                {
                    "cache_schema_version": 1,
                    "fetched_at": "2026-08-19T12:31:00+00:00",
                    "report": report,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_fresh_report_is_marked_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_cache(Path(tmp), valid_report())
            provider = FileAdvisoryProvider(path)

            snapshot = provider.get_snapshot(
                now=datetime(2026, 8, 19, 12, 40, tzinfo=timezone.utc)
            )

            self.assertTrue(snapshot["available"])
            self.assertTrue(snapshot["fresh"])
            self.assertFalse(snapshot["stale"])
            self.assertEqual(snapshot["age_seconds"], 600)
            self.assertEqual(snapshot["report"]["analysis_id"], "test-analysis-id")

    def test_report_older_than_30_minutes_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_cache(Path(tmp), valid_report())
            provider = FileAdvisoryProvider(path)

            snapshot = provider.get_snapshot(
                now=datetime(2026, 8, 19, 13, 1, tzinfo=timezone.utc)
            )

            self.assertTrue(snapshot["available"])
            self.assertFalse(snapshot["fresh"])
            self.assertTrue(snapshot["stale"])
            self.assertEqual(snapshot["age_seconds"], 1860)

    def test_missing_cache_is_normal_unavailable_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FileAdvisoryProvider(Path(tmp) / "missing.json")
            snapshot = provider.get_snapshot()

            self.assertFalse(snapshot["available"])
            self.assertFalse(snapshot["fresh"])
            self.assertTrue(snapshot["stale"])

    def test_unsafe_control_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = valid_report()
            report["control_actions_supported"] = True
            path = self._write_cache(Path(tmp), report)

            with self.assertRaises(AdvisoryError):
                FileAdvisoryProvider(path).get_snapshot()

    def test_wrong_source_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = valid_report()
            report["source_id"] = "other-device"
            path = self._write_cache(Path(tmp), report)

            with self.assertRaises(AdvisoryError):
                FileAdvisoryProvider(path).get_snapshot()

    def test_api_is_read_only_and_does_not_contact_core(self):
        core = FakeCore()
        snapshot = {
            "available": True,
            "configured": True,
            "source": "local-cache",
            "fresh": True,
            "stale": False,
            "report": valid_report(),
        }
        app = WebApplication(
            core,
            advisory=StaticAdvisoryProvider(snapshot),
        )

        response = app.handle("GET", "/api/v1/ai/advisory")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertEqual(
            response.payload["advisory"]["report"]["analysis_id"],
            "test-analysis-id",
        )
        self.assertEqual(core.requests, [])

    def test_missing_provider_returns_read_only_unavailable_state(self):
        core = FakeCore()
        response = WebApplication(core).handle("GET", "/api/v1/ai/advisory")

        self.assertEqual(response.status, 200)
        self.assertFalse(response.payload["advisory"]["available"])
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
