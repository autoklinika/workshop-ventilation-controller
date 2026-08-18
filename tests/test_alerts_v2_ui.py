from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class AlertsV2UiTest(unittest.TestCase):
    def test_alerts_v2_uses_dedicated_operator_layout(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "alerts-v2.css").read_text(encoding="utf-8")

        self.assertIn('href="/alerts-v2.css"', html)
        self.assertIn('class="v2-alerts-hero"', html)
        self.assertIn('id="alertsConnectionStatus"', html)
        self.assertIn('id="alertsActiveCount"', html)
        self.assertIn('id="alertsUnackCount"', html)
        self.assertIn('id="alertsHistoryCount"', html)
        self.assertIn('id="alertsActiveList"', html)
        self.assertIn('id="alertsHistoryBody"', html)
        self.assertIn(".v2-alert-card.critical", css)
        self.assertIn(".v2-alert-card.warning", css)

    def test_alerts_v2_keeps_core_owned_alert_contract(self) -> None:
        js = (STATIC / "alerts.js").read_text(encoding="utf-8")

        self.assertIn('fetch("/api/v1/alerts"', js)
        self.assertIn('fetch("/api/v1/alerts/ack"', js)
        self.assertIn('alert.alert_id', js)
        self.assertIn('alert.acknowledged', js)
        self.assertNotIn('/api/v1/manual/', js)
        self.assertNotIn('/api/v1/command', js)

    def test_static_server_exposes_alerts_v2_css(self) -> None:
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"alerts-v2.css"', server)


if __name__ == "__main__":
    unittest.main()
