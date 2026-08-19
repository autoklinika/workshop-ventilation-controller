import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class WebAiPanelTest(unittest.TestCase):
    def test_dashboard_contains_ai_output_fields(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="aiStatus"', html)
        self.assertIn('id="aiHeadline"', html)
        self.assertIn('id="aiSummary"', html)
        self.assertIn('id="aiRecommendation"', html)
        self.assertIn('id="aiDataQuality"', html)
        self.assertIn('id="aiUpdatedAt"', html)

    def test_dashboard_reads_only_local_ai_endpoint(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")

        self.assertIn('/api/v1/ai/advisory', js)
        self.assertIn("aiAdvisory();", js)
        self.assertIn("setInterval(aiAdvisory, 60000)", js)

        self.assertNotIn("control_actions_supported=true", js)
        self.assertNotIn("/api/v1/manual/", js)
        self.assertNotIn('method:"POST"', js)
        self.assertNotIn('method: "POST"', js)

    def test_all_v12_statuses_have_explicit_presentation(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")

        self.assertIn("no_anomaly_detected:", js)
        self.assertIn("attention:", js)
        self.assertIn("anomaly:", js)
        self.assertIn("insufficient_data:", js)

        self.assertIn('"BRAK ANOMALII"', js)
        self.assertIn('"WYMAGA UWAGI"', js)
        self.assertIn('"ANOMALIA"', js)
        self.assertIn('"NIEWYSTARCZAJĄCE DANE"', js)

    def test_stale_state_overrides_visual_status(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")

        self.assertIn("snapshot.stale === true", js)
        self.assertIn('"ANALIZA NIEAKTUALNA"', js)
        self.assertIn("report.window_end", js)
        self.assertIn("snapshot.age_seconds", js)

    def test_operator_fields_are_rendered_from_validated_report(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")

        self.assertIn("result.analysis_pl", js)
        self.assertIn("result.operator_recommendation_pl", js)
        self.assertIn("result.data_quality_pl", js)
        self.assertIn("report.analysis_id", js)


if __name__ == "__main__":
    unittest.main()
