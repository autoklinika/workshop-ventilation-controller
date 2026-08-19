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
        self.assertIn('id="alertsView"', html)
        self.assertIn('data-route="/"', html)
        self.assertIn('data-route="/control"', html)
        self.assertIn('data-route="/alerts"', html)
        self.assertIn('<span>ALERTY</span>', html)
        self.assertIn('src="/alerts.js"', html)

    def test_dashboard_view_remains_read_only(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn('/api/v1/state', js)
        self.assertIn('/api/v1/config', js)
        self.assertIn('/api/v1/weather', js)
        self.assertNotIn('/api/v1/manual/', js)
        self.assertNotIn('method:"POST"', js)
        self.assertNotIn('method: "POST"', js)
        self.assertIn("Math.round(n*10)", js)

    def test_shell_switches_three_views_without_document_navigation(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn("history.pushState", js)
        self.assertIn('target !== "/"', js)
        self.assertIn('target !== "/control"', js)
        self.assertIn('target !== "/alerts"', js)
        self.assertIn("alertsView.hidden", js)
        self.assertIn("event.preventDefault()", js)
        self.assertIn('a[href="/alerts"]', js)
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

    def test_zones_present_both_production_tacho_channels(self):
        html = (STATIC / "control.html").read_text(encoding="utf-8")
        js = (STATIC / "tacho.js").read_text(encoding="utf-8")

        self.assertIn('id="supplyRpm"', html)
        self.assertIn('id="extractRpm"', html)
        self.assertIn('id="supplyTachoChip"', html)
        self.assertIn('id="extractTachoChip"', html)

        self.assertIn('renderTachoChannel(tacho, "supply"', js)
        self.assertIn('renderTachoChannel(tacho, "extract"', js)
        self.assertIn('tacho.supply && tacho.extract', js)
        self.assertIn('channel.frequency_hz', js)
        self.assertIn('channel.line_name', js)
        self.assertIn('"NIEPEŁNE"', js)

    def test_global_alert_modal_is_driven_only_by_core_alert_records(self):
        alerts = (STATIC / "alerts.js").read_text(encoding="utf-8")
        tacho = (STATIC / "tacho.js").read_text(encoding="utf-8")
        css = (STATIC / "sidebar.css").read_text(encoding="utf-8")

        self.assertIn('overlay.id = "globalSystemAlert"', alerts)
        self.assertIn('overlay.setAttribute("role", "alertdialog")', alerts)
        self.assertIn('overlay.setAttribute("aria-modal", "true")', alerts)
        self.assertIn('BŁĄD SYSTEMU', alerts)
        self.assertIn('/api/v1/alerts', alerts)
        self.assertIn('/api/v1/alerts/ack', alerts)
        self.assertIn('alert.alert_id', alerts)
        self.assertIn('alert.acknowledged', alerts)
        self.assertIn('alert.active === true', alerts)
        self.assertIn('event.key === "Escape"', alerts)
        self.assertIn('event.preventDefault()', alerts)
        self.assertIn('.v2-system-alert[hidden]', css)
        self.assertIn('z-index:1000', css)

        self.assertNotIn('collectGlobalSystemErrors', tacho)
        self.assertNotIn('globalAlertState', tacho)
        self.assertNotIn('globalSystemAlert', tacho)

    def test_alert_client_contains_no_system_fault_classification_rules(self):
        alerts = (STATIC / "alerts.js").read_text(encoding="utf-8")
        forbidden = (
            "hardware_ready",
            "output_state_known",
            "sensor_bus",
            "aero_bus",
            "tacho.worker_alive",
            "measurement_stale",
            "measurement_valid",
            "consecutive_failures",
            "collectGlobalSystemErrors",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, alerts)

    def test_alert_view_displays_core_active_and_persistent_history(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        alerts = (STATIC / "alerts.js").read_text(encoding="utf-8")
        self.assertIn('id="alertsActiveList"', html)
        self.assertIn('id="alertsHistoryBody"', html)
        self.assertIn('CM5 · SQLITE', html)
        self.assertIn('payload.active', alerts)
        self.assertIn('payload.history', alerts)
        self.assertIn('alert.active_since', alerts)
        self.assertIn('alert.acknowledged_at', alerts)
        self.assertIn('alert.cleared_at', alerts)
        self.assertIn('alert.occurrences', alerts)

    def test_alert_and_control_routes_return_same_application_shell(self):
        server = (WEB / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/control", "/control/", "/alerts", "/alerts/"', server)
        self.assertIn('relative = "index.html"', server)
        self.assertIn('"alerts.js"', server)

    def test_sidebar_css_locks_shell_geometry(self):
        css = (STATIC / "sidebar.css").read_text(encoding="utf-8")
        self.assertIn("position:fixed", css)
        self.assertIn("top:0", css)
        self.assertIn(".v2-shell-view[hidden]", css)
        self.assertIn("margin-left:118px", css)

    def test_dashboard_ai_placeholder_remains_explicit(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("AI · ANALIZA SYSTEMU", html)
        self.assertIn("OCZEKIWANIE NA AI", html)
        self.assertIn("Brak analizy AI", html)
        self.assertIn("Po uruchomieniu integracji będą tutaj prezentowane bieżące wnioski z telemetrii wentylacji.", html)


if __name__ == "__main__":
    unittest.main()
