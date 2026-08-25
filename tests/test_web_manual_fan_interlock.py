import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "ventilation_core" / "web" / "static" / "app.js"


class WebManualFanInterlockTest(unittest.TestCase):
    def test_unrelated_active_alerts_do_not_disable_manual_ec_controls(self) -> None:
        js = APP_JS.read_text(encoding="utf-8")

        self.assertIn(
            "const fanDisabled = !state.hardware_ready || !state.output_state_known || fanCommandPending;",
            js,
        )
        self.assertNotIn(
            "(Array.isArray(state.active_alarms) && state.active_alarms.length > 0) || fanCommandPending",
            js,
        )

    def test_gui_keeps_core_hardware_safety_flags_as_interlock(self) -> None:
        js = APP_JS.read_text(encoding="utf-8")

        self.assertIn("!state.hardware_ready", js)
        self.assertIn("!state.output_state_known", js)
        self.assertIn("ui.applyFansButton.disabled = fanDisabled", js)
        self.assertIn("ui.supplyToggle.disabled = fanDisabled", js)
        self.assertIn("ui.extractToggle.disabled = fanDisabled", js)

    def test_stop_remains_available_independently_of_active_alerts(self) -> None:
        js = APP_JS.read_text(encoding="utf-8")

        self.assertIn("ui.stopFansButton.disabled = fanCommandPending", js)


if __name__ == "__main__":
    unittest.main()
