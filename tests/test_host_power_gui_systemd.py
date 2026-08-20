from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class HostPowerGuiSystemdTest(unittest.TestCase):
    def test_gui_adds_power_tile_after_service_and_two_action_modal(self) -> None:
        js = (STATIC / "host-power.js").read_text(encoding="utf-8")
        css = (STATIC / "host-power.css").read_text(encoding="utf-8")
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(encoding="utf-8")

        self.assertIn('insertAdjacentElement("afterend", tile)', js)
        self.assertIn('String(label || "").trim().toUpperCase() === "SERWIS"', js)
        self.assertIn("ZASILANIE", js)
        self.assertIn("⏻", js)
        self.assertIn("WYŁĄCZ", js)
        self.assertIn("RESTART", js)
        self.assertIn('fetch(POWER_ENDPOINT', js)
        self.assertIn('method: "POST"', js)
        self.assertIn('JSON.stringify({ action })', js)
        self.assertIn("Trwa wyłączanie…", js)
        self.assertIn("Trwa restart…", js)
        self.assertNotIn("Wybierz operację dla sterownika CM5.", js)
        self.assertNotIn("Operacja zostanie wykonana przez system Linux.", js)
        self.assertNotIn("Polecenie przyjęte. CM5", js)
        self.assertNotIn("systemctl", js)
        self.assertNotIn("/api/v1/manual/", js)
        self.assertIn("v2-host-power-card", css)
        self.assertIn(".v2-host-power-status:empty{display:none}", css)
        self.assertNotIn("#b52d35", css)
        self.assertNotIn("#871f27", css)
        self.assertIn('"host-power.js"', server)
        self.assertIn('"host-power.css"', server)
        self.assertIn('host_power_js = (self.server.static_root / "host-power.js").resolve()', server)

    def test_power_modal_reloads_after_cm5_goes_offline_and_recovers(self) -> None:
        js = (STATIC / "host-power.js").read_text(encoding="utf-8")

        self.assertIn('window.addEventListener("cm5-watchdog-offline"', js)
        self.assertIn('window.addEventListener("cm5-watchdog-online"', js)
        self.assertIn("awaitingHostRecovery", js)
        self.assertIn("hostCommunicationLost = true", js)
        self.assertIn("if (!awaitingHostRecovery || !hostCommunicationLost) return;", js)
        self.assertIn("window.location.reload();", js)
        self.assertIn("armRecoveryReload(action);", js)
        self.assertIn("clearRecoveryReload();", js)

    def test_privileged_agent_unit_is_local_hardened_and_not_network_exposed(self) -> None:
        unit = (ROOT / "deploy" / "systemd" / "wvc-host-power.service").read_text(encoding="utf-8")
        web_unit = (ROOT / "deploy" / "systemd" / "wvc-web-ui.service").read_text(encoding="utf-8")

        self.assertIn("User=root", unit)
        self.assertIn("Group=wentylacja", unit)
        self.assertIn("RuntimeDirectory=wvc-host-power", unit)
        self.assertIn("RuntimeDirectoryMode=0770", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertNotIn("AF_INET", unit)
        self.assertNotIn("AF_INET6", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ProtectHome=read-only", unit)
        self.assertIn("RestrictSUIDSGID=true", unit)
        self.assertIn("ventilation_core.host_power_agent", unit)
        self.assertNotIn("sudo", unit)

        self.assertIn("wvc-host-power.service", web_unit)
        self.assertIn("AF_NETLINK", web_unit)

    def test_core_alert_and_ai_send_boundaries_remain_untouched(self) -> None:
        import hashlib

        def blob_sha(path: Path) -> str:
            data = path.read_bytes()
            return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

        self.assertEqual(
            blob_sha(ROOT / "src" / "ventilation_core" / "runtime" / "server.py"),
            "bb906449e7aa4582c97d9db60655dd3a9fc101ce",
        )
        self.assertEqual(
            blob_sha(ROOT / "src" / "ventilation_core" / "application" / "alert_registry.py"),
            "097dbd9ad975e6f6c1a8239f56495cf1284bdd41",
        )
        self.assertEqual(
            blob_sha(ROOT / "src" / "ventilation_core" / "infrastructure" / "sqlite_alert_store.py"),
            "6467e5d7da7d7c7706957f59df433fac8896b08b",
        )
        self.assertEqual(
            blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "agent.py"),
            "54cfbcaa2fa1b5a3442cf7392e69097238d0a096",
        )
        self.assertEqual(
            blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "http_client.py"),
            "1f43c280117f9ecdff63e539e0d5fec380aee26b",
        )


if __name__ == "__main__":
    unittest.main()
