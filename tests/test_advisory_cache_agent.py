from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ventilation_core.advisory.agent import AdvisoryAgent
from ventilation_core.advisory.cache import AdvisoryCache


SOURCE_ID = "workshop-ventilation-cm5-01"


def report(analysis_id: str) -> dict:
    return {
        "delivery_schema_version": 1,
        "analysis_id": analysis_id,
        "source_id": SOURCE_ID,
        "window_start": "2026-08-10T15:15:00Z",
        "window_end": "2026-08-10T15:30:00Z",
        "created_at": "2026-08-10T15:37:36Z",
        "sample_count": 180,
        "model": "qwen3.6:35b",
        "prompt_version": "ventilation-v10-baseline-safe",
        "advisory_only": True,
        "experimental": True,
        "control_actions_supported": False,
        "result": {
            "schema_version": 2,
            "status": "no_anomaly_detected",
            "analysis_pl": "Raport testowy.",
            "operator_recommendation_pl": "Treść doradcza.",
            "data_quality_pl": "Dane kompletne.",
        },
    }


class FakeClient:
    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.calls = 0

    def fetch_latest(self, source_id: str):
        self.calls += 1
        if source_id != SOURCE_ID:
            raise AssertionError("unexpected source")
        return self.payload


class AdvisoryCacheAgentTest(unittest.TestCase):
    def test_cache_is_local_json_envelope_and_agent_skips_same_analysis(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "ai-advisory.json"
        cache = AdvisoryCache(path)
        client = FakeClient(report("analysis-1"))
        agent = AdvisoryAgent(
            client=client,  # type: ignore[arg-type]
            cache=cache,
            source_id=SOURCE_ID,
            poll_interval_seconds=60,
        )

        self.assertTrue(agent.fetch_once())
        first_bytes = path.read_bytes()
        stored = json.loads(first_bytes.decode("utf-8"))
        self.assertEqual(stored["cache_schema_version"], 1)
        self.assertEqual(stored["report"]["analysis_id"], "analysis-1")
        self.assertFalse(stored["report"]["control_actions_supported"])

        self.assertFalse(agent.fetch_once())
        self.assertEqual(path.read_bytes(), first_bytes)
        self.assertEqual(client.calls, 2)

    def test_no_remote_analysis_does_not_create_cache(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "ai-advisory.json"
        agent = AdvisoryAgent(
            client=FakeClient(None),  # type: ignore[arg-type]
            cache=AdvisoryCache(path),
            source_id=SOURCE_ID,
            poll_interval_seconds=60,
        )
        self.assertFalse(agent.fetch_once())
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
