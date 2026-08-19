from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class HistoryTabStage2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.js = (STATIC / "history.js").read_text(encoding="utf-8")
        self.css = (STATIC / "history.css").read_text(encoding="utf-8")
        self.server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

    def test_history_navigation_is_enabled_as_client_route(self) -> None:
        self.assertIn('item.textContent.trim() === "HISTORIA"', self.js)
        self.assertIn('link.href = "/history"', self.js)
        self.assertIn('link.dataset.route = "/history"', self.js)
        self.assertIn('history.pushState({ v2Route: "/history" }', self.js)
        self.assertIn('window.location.pathname.startsWith("/history")', self.js)

    def test_history_uses_stable_backend_series_api_only(self) -> None:
        self.assertIn('historyRequest("/api/v1/history/series")', self.js)
        self.assertIn('historyRequest("/api/v1/history/status")', self.js)
        self.assertIn('historyPost("/api/v1/history/series/query"', self.js)
        self.assertIn('resolution: "auto"', self.js)
        self.assertNotIn('/api/v1/history/query', self.js)
        self.assertNotIn('/api/v1/manual/', self.js)
        self.assertNotIn('/api/v1/manual/fans', self.js)
        self.assertNotIn('/api/v1/manual/aero', self.js)

    def test_history_exposes_sensor_fan_setpoint_duct_and_aero_groups(self) -> None:
        for token in (
            '"zone1.air.pm1_0"',
            '"zone1.air.pm2_5"',
            '"zone1.air.pm4_0"',
            '"zone1.air.pm10_0"',
            '"zone1.air.voc_index"',
            '"zone1.air.nox_index"',
            '"zone1.air.temperature"',
            '"zone1.air.humidity"',
            '"zone1.fans.supply.rpm"',
            '"zone1.fans.extract.rpm"',
            '"zone1.fans.supply.setpoint_v"',
            '"zone1.fans.extract.setpoint_v"',
            '"zone1.duct.supply.temperature"',
            '"zone1.duct.extract.temperature"',
            '"zone2.air.pm2_5"',
            '"zone2.aero.supply_temperature"',
            '"zone2.aero.extract_temperature"',
            '"zone2.aero.outdoor_temperature"',
            '"zone2.aero.fan1_percent"',
            '"zone2.aero.fan2_percent"',
            '"zone2.aero.humidity"',
        ):
            self.assertIn(token, self.js)

    def test_hmi_layout_has_fixed_chart_and_no_horizontal_scrolling(self) -> None:
        self.assertIn("grid-template-columns:repeat(7,minmax(0,1fr));", self.css)
        self.assertIn("height:512px", self.css)
        self.assertIn("min-width:0", self.css)
        self.assertIn("overflow:hidden", self.css)
        self.assertNotIn("overflow-x:auto", self.css)
        self.assertNotIn("overflow-x:scroll", self.css)

    def test_chart_renders_backend_points_and_breaks_at_backend_gaps(self) -> None:
        self.assertIn('const value = resolution === "raw" ? point.value : point.avg;', self.js)
        self.assertIn('if (point.gap_before === true) drawing = false;', self.js)
        self.assertIn('if (value === null || !Number.isFinite(time))', self.js)
        self.assertIn('payload.range && payload.range.start', self.js)
        self.assertIn('payload.range && payload.range.end', self.js)
        self.assertIn('firstSeries.missing_points', self.js)
        self.assertIn('firstSeries.gap_count', self.js)

    def test_chart_modal_matches_accepted_large_fly_out_pattern(self) -> None:
        self.assertIn("const HISTORY_MODAL_OPEN_MS = 280;", self.js)
        self.assertIn("const HISTORY_MODAL_CLOSE_MS = 240;", self.js)
        self.assertIn("sourceCard.getBoundingClientRect()", self.js)
        self.assertIn("targetCard.getBoundingClientRect()", self.js)
        self.assertIn("sourceCenterX - targetCenterX", self.js)
        self.assertIn("sourceCenterY - targetCenterY", self.js)
        self.assertIn("card.animate([", self.js)
        self.assertIn("width:94vw", self.css)
        self.assertIn("height:92vh", self.css)
        self.assertIn("backdrop-filter:blur(10px)", self.css)
        self.assertIn("transform-origin:50% 50%", self.css)

    def test_history_modal_is_presentation_only(self) -> None:
        self.assertIn("syncHistoryChartModal();", self.js)
        self.assertIn("historyRenderSvg(document.getElementById(\"historyModalSvg\"), historyClient.payload)", self.js)
        self.assertNotIn('historyPost("/api/v1/history/series/query"', self.js.split("function openHistoryChartModal", 1)[1])

    def test_static_server_serves_history_route_and_bundles_assets(self) -> None:
        self.assertIn('"/history", "/history/"', self.server)
        self.assertIn('"history.js"', self.server)
        self.assertIn('"history.css"', self.server)
        self.assertIn('(\"zone-detail.js\", \"history.js\")', self.server)
        self.assertIn('(\"zone-detail.css\", \"history.css\")', self.server)


if __name__ == "__main__":
    unittest.main()
