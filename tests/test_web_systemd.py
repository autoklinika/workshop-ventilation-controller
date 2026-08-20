import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebSystemdTest(unittest.TestCase):
    def test_web_ui_service_is_independent_client_of_core(self):
        unit = (ROOT / "deploy/systemd/wvc-web-ui.service").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/bin/python3 -m ventilation_core.web.main", unit)
        self.assertIn("After=network-online.target ventilation-core.service", unit)
        self.assertNotIn("Requires=ventilation-core.service", unit)
        self.assertIn("User=wentylacja", unit)
        self.assertIn("Group=wentylacja", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", unit)
        self.assertIn("ProtectHome=read-only", unit)
        self.assertNotIn("ProtectHome=true", unit)

    def test_web_ui_sandbox_uses_optional_nvme_history_directory(self):
        unit = (ROOT / "deploy/systemd/wvc-web-ui.service").read_text(encoding="utf-8")
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ReadWritePaths=-/srv/wvc-data/workshop-ventilation", unit)
        self.assertNotIn("ReadWritePaths=/var/lib/workshop-ventilation", unit)
        self.assertNotIn("RequiresMountsFor=/srv/wvc-data", unit)

    def test_web_env_points_history_and_caches_to_nvme(self):
        env = (ROOT / "deploy/cm5/web/wvc-web-ui.env.example").read_text(encoding="utf-8")
        self.assertIn("WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock", env)
        self.assertIn("WVC_WEB_HOST=0.0.0.0", env)
        self.assertIn("WVC_WEB_PORT=8088", env)
        for path in (
            "WVC_WEB_TELEMETRY_DATABASE=/srv/wvc-data/workshop-ventilation/telemetry.sqlite3",
            "WVC_WEB_ALERT_DATABASE=/srv/wvc-data/workshop-ventilation/alerts.sqlite3",
            "WVC_WEB_WEATHER_SNAPSHOT=/srv/wvc-data/workshop-ventilation/weather.json",
            "WVC_WEB_AI_ADVISORY_CACHE=/srv/wvc-data/workshop-ventilation/ai-advisory.json",
        ):
            self.assertIn(path, env)
        self.assertNotIn("WVC_WEB_WEATHER_LATITUDE", env)
        self.assertNotIn("WVC_WEB_WEATHER_LONGITUDE", env)
        self.assertNotIn("WVC_WEB_WEATHER_USER_AGENT", env)

    def test_weather_service_owns_external_weather_configuration(self):
        unit = (ROOT / "deploy/systemd/wvc-weather.service").read_text(encoding="utf-8")
        env = (ROOT / "deploy/cm5/weather/wvc-weather.env.example").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/bin/python3 -m ventilation_core.weather.main", unit)
        self.assertIn("EnvironmentFile=-/etc/default/wvc-weather", unit)
        self.assertIn("ReadWritePaths=/srv/wvc-data/workshop-ventilation", unit)
        self.assertIn("RequiresMountsFor=/srv/wvc-data", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", unit)
        self.assertNotIn("ventilation-core.service", unit)
        self.assertIn("WVC_WEATHER_LATITUDE=", env)
        self.assertIn("WVC_WEATHER_LONGITUDE=", env)
        self.assertIn("WVC_WEATHER_USER_AGENT=", env)
        self.assertIn("WVC_WEATHER_CACHE=/srv/wvc-data/workshop-ventilation/weather.json", env)

    def test_manual_sliders_start_at_minimum_operating_voltage(self):
        html = (ROOT / "src/ventilation_core/web/static/control.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'id="supplySlider" class="voltage-slider" type="range" min="1" max="10" step="0.5" value="1" disabled',
            html,
        )
        self.assertIn(
            'id="extractSlider" class="voltage-slider" type="range" min="1" max="10" step="0.5" value="1" disabled',
            html,
        )


if __name__ == "__main__":
    unittest.main()
