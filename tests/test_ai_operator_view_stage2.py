from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.advisory.client import validate_advisory_delivery


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"
SOURCE_ID = "workshop-ventilation-cm5-01"


def payload_with_operator_view() -> dict:
    return {
        "delivery_schema_version": 1,
        "analysis_id": "a73a3120-b120-45ad-bc80-470e2971d2db",
        "source_id": SOURCE_ID,
        "window_start": "2026-08-19T15:30:00Z",
        "window_end": "2026-08-19T15:45:00Z",
        "created_at": "2026-08-19T15:48:30Z",
        "sample_count": 179,
        "model": "qwen3.6:35b",
        "prompt_version": "ventilation-v12.2-adverse-trend-gate",
        "advisory_only": True,
        "experimental": True,
        "control_actions_supported": False,
        "result": {
            "schema_version": 2,
            "status": "attention",
            "analysis_pl": "Pełny techniczny raport pozostaje dostępny.",
            "operator_recommendation_pl": "Pełna rekomendacja techniczna.",
            "data_quality_pl": "Pełna diagnostyka jakości danych.",
            "operator_view": {
                "schema_version": 1,
                "status_label_pl": "WYMAGA UWAGI",
                "headline_pl": "Wzrost VOC Index — strefa 1",
                "summary_pl": "VOC Index — strefa 1: wzrósł z 84 do 166.",
                "recommendation_pl": "Obserwuj kolejne okna pomiarowe.",
                "data_quality_short_pl": "Dane kompletne · 179 próbek",
            },
        },
    }


class AiOperatorViewStage2Test(unittest.TestCase):
    def test_client_accepts_operator_view_without_interpreting_it(self) -> None:
        payload = payload_with_operator_view()
        validated = validate_advisory_delivery(payload, expected_source_id=SOURCE_ID)
        self.assertIs(validated, payload)
        self.assertEqual(
            validated["result"]["operator_view"]["headline_pl"],
            "Wzrost VOC Index — strefa 1",
        )

    def test_client_rejects_broken_operator_view_shape(self) -> None:
        payload = payload_with_operator_view()
        del payload["result"]["operator_view"]["summary_pl"]
        with self.assertRaisesRegex(RuntimeError, "operator_view field 'summary_pl'"):
            validate_advisory_delivery(payload, expected_source_id=SOURCE_ID)

    def test_dashboard_loads_stage2_renderer_after_transport_renderer(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        transport = html.index('src="/dashboard-live.js"')
        operator = html.index('src="/ai-operator-view.js"')
        self.assertLess(transport, operator)

    def test_stage2_renderer_uses_backend_copy_verbatim_with_legacy_fallback(self) -> None:
        js = (STATIC / "ai-operator-view.js").read_text(encoding="utf-8")
        self.assertIn("operatorView.status_label_pl", js)
        self.assertIn("operatorView.headline_pl", js)
        self.assertIn("operatorView.summary_pl", js)
        self.assertIn("operatorView.recommendation_pl", js)
        self.assertIn("operatorView.data_quality_short_pl", js)
        self.assertIn("result.analysis_pl", js)
        self.assertIn("result.operator_recommendation_pl", js)
        self.assertIn("result.data_quality_pl", js)

        self.assertNotIn("slope_per_minute", js)
        self.assertNotIn("voc_index", js)
        self.assertNotIn("pm2_5", js)
        self.assertNotIn("fetch(\"http://", js)
        self.assertNotIn("method: \"POST\"", js)

    def test_static_server_allows_stage2_renderer(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"ai-operator-view.js"', server)


if __name__ == "__main__":
    unittest.main()
