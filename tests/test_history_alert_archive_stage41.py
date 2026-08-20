from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class HistoryAlertArchiveStage41Test(unittest.TestCase):
    def setUp(self) -> None:
        self.js = (STATIC / "history-h41-alerts.js").read_text(encoding="utf-8")
        self.css = (STATIC / "history-h41-alerts.css").read_text(encoding="utf-8")
        self.server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

    def test_alerts_page_keeps_only_active_alert_presentation(self) -> None:
        self.assertIn('view.querySelector("#alertsHistoryBody")', self.js)
        self.assertIn('view.querySelector("#alertsHistoryCount")', self.js)
        self.assertIn('section.remove()', self.js)
        self.assertIn('card.remove()', self.js)
        self.assertIn("Bieżące alerty wymagające uwagi operatora", self.js)

    def test_history_page_gets_cleared_alert_archive(self) -> None:
        self.assertIn('section.id = "historyAlertArchive"', self.js)
        self.assertIn("Historia alertów", self.js)
        self.assertIn("Aktywne alerty pozostają w zakładce ALERTY", self.js)
        self.assertIn("alert.active !== true", self.js)
        self.assertIn('typeof alert.cleared_at === "string"', self.js)

    def test_archive_grouping_uses_backend_severity_only(self) -> None:
        self.assertIn("historyH41SeverityClass(alert.severity)", self.js)
        self.assertIn('label: "KRYTYCZNE"', self.js)
        self.assertIn('label: "OSTRZEŻENIA"', self.js)
        self.assertIn('label: "POZOSTAŁE"', self.js)
        for forbidden in (
            "sensor_bus",
            "sen55_",
            "zigbee_",
            "aero_bus",
            "dac_",
            "tacho_",
            "service_",
            "kamod_",
        ):
            self.assertNotIn(forbidden, self.js.lower())

    def test_archive_is_read_only_and_uses_existing_alert_endpoint(self) -> None:
        self.assertIn('fetch("/api/v1/alerts"', self.js)
        self.assertNotIn('method: "POST"', self.js)
        self.assertNotIn("/api/v1/alerts/ack", self.js)
        self.assertNotIn("data-alert-ack", self.js)

    def test_archive_contains_full_existing_alert_metadata(self) -> None:
        for token in (
            "alert.message",
            "alert.detail",
            "alert.source",
            "alert.active_since",
            "alert.acknowledged_at",
            "alert.cleared_at",
            "alert.occurrences",
            "alert.alert_id",
        ):
            self.assertIn(token, self.js)

    def test_stage41_assets_are_bundled_after_h4(self) -> None:
        self.assertIn('"history-h41-alerts.js"', self.server)
        self.assertIn('"history-h41-alerts.css"', self.server)
        self.assertIn("h41_alert_js.read_bytes()", self.server)
        self.assertIn("h41_alert_css.read_bytes()", self.server)
        self.assertLess(
            self.server.index('h4_storage_js = (self.server.static_root / "history-h4-storage.js")'),
            self.server.index('h41_alert_js = (self.server.static_root / "history-h41-alerts.js")'),
        )

    def test_hmi_layout_allows_vertical_history_archive(self) -> None:
        self.assertIn(".v2-history-alert-archive", self.css)
        self.assertIn(".v2-history-alert-groups", self.css)
        self.assertIn("@media(max-width:1280px)", self.css)
        self.assertNotIn("position:fixed", self.css)

    def test_ai_telemetry_send_logic_remains_byte_for_byte_unchanged(self) -> None:
        agent = ROOT / "src" / "ventilation_core" / "telemetry" / "agent.py"
        client = ROOT / "src" / "ventilation_core" / "telemetry" / "http_client.py"
        self.assertEqual(
            git_blob_sha(agent),
            "54cfbcaa2fa1b5a3442cf7392e69097238d0a096",
        )
        self.assertEqual(
            git_blob_sha(client),
            "1f43c280117f9ecdff63e539e0d5fec380aee26b",
        )


if __name__ == "__main__":
    unittest.main()
