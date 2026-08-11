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

    def test_web_env_keeps_core_socket_and_bind_address_explicit(self):
        env = (ROOT / "deploy/cm5/web/wvc-web-ui.env.example").read_text(encoding="utf-8")
        self.assertIn("WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock", env)
        self.assertIn("WVC_WEB_HOST=0.0.0.0", env)
        self.assertIn("WVC_WEB_PORT=8088", env)


if __name__ == "__main__":
    unittest.main()
