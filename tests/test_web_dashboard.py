import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"
WEB = ROOT / "src" / "ventilation_core" / "web"


class WebDashboardV2StructureTest(unittest.TestCase):
    def test_v2_shell_has_one_fixed_sidebar_and_no_topbar(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('class="v2-sidebar"'), 1)
        self.assertNotIn('class="v2-topbar"', html)
        self.assertIn('id="viewHost"', html)
        self.assertIn('id="dashboardView"', html)
        self.assertIn('id="controlView"', html)
        self.assertIn('data-route="/"', html)
        self.assertIn('data-route="/control"', html)

    def test_dashboard_view_remains_read_only(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn('/api/v1/state', js)
        self.assertIn('/api/v1/config', js)
        self.assertIn('/api/v1/weather', js)
        self.assertNotIn('/api/v1/manual/', js)
        self.assertNotIn('method:"POST"', js)
        self.assertNotIn('method: "POST"', js)
        self.assertIn("Math.round(n*10)", js)

    def test_shell_switches_views_without_document_navigation(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn("history.pushState", js)
        self.assertIn("dashboardView.hidden", js)
        self.assertIn("controlView.hidden", js)
        self.assertIn("event.preventDefault()", js)
        self.assertIn('fetch("/control.html"', js)
        self.assertIn('loadV2Script("/app.js")', js)
        self.assertIn('loadV2Script("/tacho.js")', js)

    def test_control_source_keeps_manual_controls(self):
        html = (STATIC / "control.html").read_text(encoding="utf-8")
        self.assertIn('id="applyFansButton"', html)
        self.assertIn('id="stopFansButton"', html)
        self.assertIn('data-aero-speed="0"', html)
        self.assertIn('src="/app.js"', html)
        self.assertIn('src="/tacho.js"', html)

    def test_control_route_returns_same_application_shell(self):
        server = (WEB / "server.py").read_text(encoding="utf-8")
        self.assertIn('request_path in ("", "/", "/control", "/control/")', server)
        self.assertIn('relative = "index.html"', server)

    def test_sidebar_css_locks_shell_geometry(self):
        css = (STATIC / "sidebar.css").read_text(encoding="utf-8")
        self.assertIn("position:fixed", css)
        self.assertIn("top:0", css)
        self.assertIn(".v2-shell-view[hidden]", css)
        self.assertIn("margin-left:118px", css)

    def test_dashboard_placeholders_remain_explicit(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("TRENDY", html)
        self.assertIn("OSTATNIE 24H", html)
        self.assertIn("oczekiwanie na integrację danych historycznych", html)
        self.assertIn("Brak historii zdarzeń", html)


if __name__ == "__main__":
    unittest.main()
