from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class HistoryH22Test(unittest.TestCase):
    def setUp(self) -> None:
        self.js = (STATIC / "history-h22.js").read_text(encoding="utf-8")
        self.css = (STATIC / "history-h22.css").read_text(encoding="utf-8")
        self.server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

    def test_zoom_is_modal_only_visual_window_over_existing_payload(self) -> None:
        self.assertIn("historyClient.payload", self.js)
        self.assertIn("historyH22Payload(historyClient.payload)", self.js)
        self.assertIn("historyH21RenderSvg(svg, viewPayload)", self.js)
        self.assertIn("points: (series.points || []).filter", self.js)
        self.assertNotIn("fetch(", self.js)
        self.assertNotIn("historyPost(", self.js)
        self.assertNotIn("/api/", self.js)
        self.assertNotIn("average", self.js.lower())
        self.assertNotIn("interpolate", self.js.lower())

    def test_large_modal_supports_pinch_wheel_buttons_and_reset(self) -> None:
        self.assertIn("HISTORY_H22_MAX_SCALE = 12", self.js)
        self.assertIn("svg.onwheel", self.js)
        self.assertIn("historyH22PinchInfo", self.js)
        self.assertIn("historyH22.pointers.size >= 2", self.js)
        self.assertIn('data-history-zoom="out"', self.js)
        self.assertIn('data-history-zoom="reset"', self.js)
        self.assertIn('data-history-zoom="in"', self.js)
        self.assertIn("historyH22ResetViewport(true)", self.js)
        self.assertIn("100%", self.js)

    def test_zoomed_modal_can_pan_horizontally_without_changing_backend_data(self) -> None:
        self.assertIn("historyH22PanFrom", self.js)
        self.assertIn("HISTORY_H22_PAN_THRESHOLD_PX = 7", self.js)
        self.assertIn("event.clientX - single.x", self.js)
        self.assertIn("startCenter + shift", self.js)
        self.assertIn("historyH22ScheduleRender", self.js)
        self.assertIn("touch-action:none", self.css)
        self.assertIn("cursor:grab", self.css)
        self.assertIn("cursor:grabbing", self.css)

    def test_h21_point_readout_remains_available_in_zoom_window(self) -> None:
        self.assertIn("historyH21ShowCursor", self.js)
        self.assertIn("historyH22Geometry", self.js)
        self.assertIn("historyH21BuildBands", self.js)
        self.assertIn("historyH21BuildCursorData", self.js)

    def test_opening_modal_and_changing_history_selection_reset_zoom(self) -> None:
        self.assertIn("historyH22BaseOpenHistoryChartModal", self.js)
        self.assertIn("historyH22ResetViewport(false)", self.js)
        self.assertIn('[data-history-zone],[data-history-range],[data-history-preset]', self.js)

    def test_h22_assets_are_served_after_h21(self) -> None:
        self.assertIn('"history-h22.js"', self.server)
        self.assertIn('"history-h22.css"', self.server)
        self.assertIn('h22_js.read_bytes()', self.server)
        self.assertIn('h22_css.read_bytes()', self.server)
        self.assertLess(
            self.server.index('h21_js = (self.server.static_root / "history-h21.js")'),
            self.server.index('h22_js = (self.server.static_root / "history-h22.js")'),
        )
        self.assertLess(
            self.server.index('h21_css = (self.server.static_root / "history-h21.css")'),
            self.server.index('h22_css = (self.server.static_root / "history-h22.css")'),
        )

    def test_zoom_controls_fit_touch_hmi_header(self) -> None:
        self.assertIn("height:46px", self.css)
        self.assertIn("width:50px", self.css)
        self.assertIn("min-width:76px", self.css)
        self.assertIn("touch-action:manipulation", self.css)
        self.assertIn("@media(max-width:1280px)", self.css)


if __name__ == "__main__":
    unittest.main()
