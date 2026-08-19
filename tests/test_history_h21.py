from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class HistoryH21Test(unittest.TestCase):
    def setUp(self) -> None:
        self.js = (STATIC / "history-h21.js").read_text(encoding="utf-8")
        self.css = (STATIC / "history-h21.css").read_text(encoding="utf-8")
        self.server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

    def test_non_negative_series_do_not_receive_negative_axis_padding(self) -> None:
        self.assertIn("const allNonNegative = rawMin >= 0;", self.js)
        self.assertIn("if (allNonNegative) low = Math.max(0, low);", self.js)
        self.assertIn("historyH21Bounds", self.js)

    def test_voc_and_nox_use_separate_stacked_scales_with_shared_time_axis(self) -> None:
        self.assertIn('const HISTORY_H21_SPLIT_SERIES = [".voc_index", ".nox_index"]', self.js)
        self.assertIn("historyH21IsGasPayload", self.js)
        self.assertIn("historyH21BuildBands", self.js)
        self.assertIn("const bandHeight", self.js)
        self.assertIn("const xFor = (time)", self.js)
        self.assertIn("historyH21BandForSeries", self.js)
        self.assertIn("v2-history-band-label", self.css)

    def test_renderer_keeps_backend_missing_values_and_explicit_gaps(self) -> None:
        self.assertIn("historySeriesValue(point, payload.resolution)", self.js)
        self.assertIn("if (value === null || !Number.isFinite(time))", self.js)
        self.assertIn("if (point.gap_before === true) drawing = false;", self.js)
        self.assertNotIn("interpolate", self.js.lower())

    def test_pointer_readout_snaps_to_backend_timestamp_without_new_query(self) -> None:
        self.assertIn("historyH21NearestTimestamp", self.js)
        self.assertIn("geometry.cursorData.maps[index].get(timestamp)", self.js)
        self.assertIn("onpointerdown", self.js)
        self.assertIn("onpointermove", self.js)
        self.assertIn('event.pointerType === "touch"', self.js)
        self.assertIn("v2-history-cursor-tooltip", self.css)
        self.assertIn("v2-history-cursor-line", self.css)
        self.assertNotIn("fetch(", self.js)
        self.assertNotIn("historyPost(", self.js)
        self.assertNotIn("/api/", self.js)

    def test_touch_drag_inspects_compact_chart_but_simple_tap_keeps_modal_behavior(self) -> None:
        self.assertIn("HISTORY_H21_TOUCH_DRAG_PX = 8", self.js)
        self.assertIn("historyH21CompactDragged = true", self.js)
        self.assertIn("event.stopImmediatePropagation();", self.js)
        self.assertIn('card.addEventListener("click"', self.js)

    def test_h21_assets_are_served_and_appended_after_h2_assets(self) -> None:
        self.assertIn('"history-h21.js"', self.server)
        self.assertIn('"history-h21.css"', self.server)
        self.assertIn('h21_js.read_bytes()', self.server)
        self.assertIn('h21_css.read_bytes()', self.server)
        js_base = self.server.index('for name in ("zone-detail.js", "history.js")')
        js_h21 = self.server.index('h21_js = (self.server.static_root / "history-h21.js")')
        css_base = self.server.index('for name in ("zone-detail.css", "history.css")')
        css_h21 = self.server.index('h21_css = (self.server.static_root / "history-h21.css")')
        self.assertLess(js_base, js_h21)
        self.assertLess(css_base, css_h21)

    def test_h21_does_not_change_history_backend_contract(self) -> None:
        for forbidden in (
            "/api/v1/history/query",
            "/api/v1/manual/",
            "setpoint",
            "trend",
            "anomaly",
        ):
            self.assertNotIn(forbidden, self.js.lower())


if __name__ == "__main__":
    unittest.main()
