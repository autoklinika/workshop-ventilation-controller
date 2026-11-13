"""Regression: production /settings is hydrated into index.html shell."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "src" / "ventilation_core" / "web"


class AutostartProductionShellTest(unittest.TestCase):
    def test_shell_loads_all_autostart_assets_after_hydration(self):
        shell = (ROOT / "static" / "dashboard-live.js").read_text()
        self.assertIn('fetch("/settings.html"', shell)
        self.assertIn('loadV2Style("/autostart.css")', shell)
        self.assertIn('await loadV2Script("/autostart.js")', shell)
        self.assertIn('host.innerHTML = source.innerHTML;', shell)

    def test_script_initializes_after_dom_content_loaded(self):
        js = (ROOT / "static" / "autostart.js").read_text()
        self.assertIn('document.readyState === "loading"', js)
        self.assertIn('initializeAutostart();', js)
        self.assertIn('autostartInitialized', js)

    def test_settings_and_css_bind_correct_tab(self):
        html = (ROOT / "static" / "settings.html").read_text()
        css = (ROOT / "static" / "autostart.css").read_text()
        self.assertIn('id="settingsTabAutostart"', html)
        self.assertIn('data-settings-panel="autostart"', html)
        self.assertIn('#settingsTabAutostart:checked~.settings-tab-panels', css)
        self.assertIn('.settings-tab-radio{position:fixed;top:0;left:0}', css)


if __name__ == "__main__":
    unittest.main()
