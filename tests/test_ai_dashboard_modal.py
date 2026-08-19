from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class AiDashboardModalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.css = (STATIC / "ai-detail.css").read_text(encoding="utf-8")
        self.js = (STATIC / "ai-operator-view.js").read_text(encoding="utf-8")

    def test_dashboard_loads_ai_detail_styles(self) -> None:
        dashboard = self.html.index('href="/dashboard.css"')
        detail = self.html.index('href="/ai-detail.css"')
        self.assertLess(dashboard, detail)

    def test_compact_ai_card_has_fixed_hmi_footprint_and_css_only_ellipsis(self) -> None:
        compact = self.css.split("body.v2-ai-detail-open", 1)[0]
        self.assertIn(".v2-ai-panel{", compact)
        self.assertIn("height:310px;", compact)
        self.assertIn("min-height:310px;", compact)
        self.assertIn("max-height:310px;", compact)
        self.assertIn("overflow:hidden;", compact)
        self.assertIn("text-overflow:ellipsis;", compact)
        self.assertIn("-webkit-line-clamp:2;", compact)
        self.assertNotIn("overflow-y:auto", compact)

    def test_tapping_card_opens_large_modal_without_expand_button(self) -> None:
        self.assertIn('document.querySelector(".v2-ai-panel")', self.js)
        self.assertIn('card.addEventListener("click"', self.js)
        self.assertIn("openAiDetailModal();", self.js)
        self.assertIn('id="aiDetailClose"', self.js)
        self.assertNotIn("aiDetailExpand", self.js)
        self.assertNotIn("v2-ai-detail-expand", self.css)

    def test_modal_reuses_rendered_client_text_verbatim(self) -> None:
        self.assertIn("target.textContent = source.textContent;", self.js)
        self.assertIn('copyAiText("aiHeadline", "aiDetailHeadline")', self.js)
        self.assertIn('copyAiText("aiSummary", "aiDetailSummary")', self.js)
        self.assertIn('copyAiText("aiRecommendation", "aiDetailRecommendation")', self.js)
        self.assertIn('copyAiText("aiDataQuality", "aiDetailDataQuality")', self.js)
        self.assertIn('copyAiText("aiUpdatedAt", "aiDetailUpdatedAt")', self.js)

        self.assertNotIn("slope_per_minute", self.js)
        self.assertNotIn("voc_index", self.js)
        self.assertNotIn("pm2_5", self.js)
        self.assertNotIn('fetch("http://', self.js)
        self.assertNotIn('method: "POST"', self.js)

    def test_modal_is_large_centered_window_with_blurred_background(self) -> None:
        detail = self.css.split(".v2-ai-detail{", 1)[1]
        self.assertIn("position:fixed;", detail)
        self.assertIn("inset:0;", detail)
        self.assertIn("display:grid;", detail)
        self.assertIn("place-items:center;", detail)
        self.assertIn("width:100vw;", detail)
        self.assertIn("height:100vh;", detail)
        self.assertIn("background:rgba(2,8,14,.72);", detail)
        self.assertIn("backdrop-filter:blur(10px);", detail)
        self.assertIn("width:94vw;", detail)
        self.assertIn("height:92vh;", detail)
        self.assertIn("border-radius:18px;", detail)
        self.assertIn(".v2-ai-detail-scroll{", detail)
        self.assertIn("overflow-x:hidden;", detail)
        self.assertIn("overflow-y:auto;", detail)

    def test_modal_flies_from_card_center_and_returns_to_it(self) -> None:
        self.assertIn("const AI_DETAIL_OPEN_MS = 280;", self.js)
        self.assertIn("const AI_DETAIL_CLOSE_MS = 240;", self.js)
        self.assertIn("function aiDetailFlightFromCard(card, detailCard)", self.js)
        self.assertIn("card.getBoundingClientRect()", self.js)
        self.assertIn("detailCard.getBoundingClientRect()", self.js)
        self.assertIn("sourceCenterX", self.js)
        self.assertIn("sourceCenterY", self.js)
        self.assertIn("targetCenterX", self.js)
        self.assertIn("targetCenterY", self.js)
        self.assertIn("sourceCenterX - targetCenterX", self.js)
        self.assertIn("sourceCenterY - targetCenterY", self.js)
        self.assertIn("function aiDetailTravelTransform", self.js)
        self.assertIn("aiDetailTravelTransform(flight, 0.08, 0.018)", self.js)
        self.assertIn("aiDetailTravelTransform(flight, 0.14, -0.008)", self.js)
        self.assertIn("const flyOut = detailCard.animate(", self.js)
        self.assertIn("const flyBack = detailCard.animate(", self.js)
        self.assertIn("cubic-bezier(.18,.84,.24,1)", self.js)
        self.assertIn("cubic-bezier(.42,0,.78,.22)", self.js)
        self.assertIn("transform-origin:50% 50%;", self.css)
        self.assertIn("will-change:transform,border-radius;", self.css)

    def test_animation_is_presentation_only_and_has_accessibility_fallback(self) -> None:
        self.assertIn('(prefers-reduced-motion: reduce)', self.js)
        self.assertIn("@media(prefers-reduced-motion:reduce)", self.css)
        self.assertIn("aiDetailCanAnimate", self.js)
        self.assertIn("cancelAiDetailAnimations", self.js)
        self.assertIn("is-transitioning", self.js)
        self.assertIn(".v2-ai-detail.is-transitioning", self.css)

        self.assertNotIn("requestAnimationFrame", self.js)
        self.assertNotIn("setInterval(", self.js)
        self.assertNotIn("setTimeout(", self.js)

    def test_static_server_allows_ai_detail_styles(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"ai-detail.css"', server)


if __name__ == "__main__":
    unittest.main()
