from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class HistoryH23Test(unittest.TestCase):
    def setUp(self) -> None:
        self.js = (STATIC / "history-h23.js").read_text(encoding="utf-8")
        self.server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

    def test_every_multi_series_payload_is_split_into_independent_bands(self) -> None:
        self.assertIn("payload.series.length > 1", self.js)
        self.assertIn("historyH23BuildBands", self.js)
        self.assertIn("seriesIndexes: [index]", self.js)
        self.assertIn("label: historyShortLabel(series.label)", self.js)
        self.assertIn("historyH21IsGasPayload = historyH23IsMultiSeriesPayload", self.js)
        self.assertIn("historyH21BuildBands = historyH23BuildBands", self.js)

    def test_single_series_keeps_one_full_height_band(self) -> None:
        self.assertIn("if (payload.series.length === 1)", self.js)
        self.assertIn("height: plotHeight", self.js)
        self.assertIn("label: null", self.js)

    def test_four_series_pm_group_has_compact_gap_strategy(self) -> None:
        self.assertIn("if (count >= 4)", self.js)
        self.assertIn("HISTORY_H23_MIN_GAP_PX", self.js)
        self.assertIn("const totalGap = gap * (count - 1)", self.js)
        self.assertIn("const bandHeight", self.js)

    def test_h23_is_presentation_only(self) -> None:
        lowered = self.js.lower()
        for forbidden in (
            "fetch(",
            "historypost(",
            "/api/",
            "interpolate",
            "aggregate",
            "setpoint =",
            "trend",
            "anomaly",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_h23_is_served_after_h22(self) -> None:
        self.assertIn('"history-h23.js"', self.server)
        self.assertIn('h23_js.read_bytes()', self.server)
        h22 = self.server.index('h22_js = (self.server.static_root / "history-h22.js")')
        h23 = self.server.index('h23_js = (self.server.static_root / "history-h23.js")')
        self.assertLess(h22, h23)


if __name__ == "__main__":
    unittest.main()
