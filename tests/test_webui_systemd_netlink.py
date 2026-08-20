from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy" / "systemd" / "wvc-web-ui.service"


class WebUiSystemdNetlinkTest(unittest.TestCase):
    def test_webui_allows_af_netlink_for_read_only_network_diagnostics(self) -> None:
        text = UNIT.read_text(encoding="utf-8")

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("RestrictAddressFamilies=")
        ]

        self.assertEqual(len(lines), 1)
        self.assertIn("AF_UNIX", lines[0])
        self.assertIn("AF_INET", lines[0])
        self.assertIn("AF_INET6", lines[0])
        self.assertIn("AF_NETLINK", lines[0])

        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("ProtectHome=read-only", text)
        self.assertIn("ReadWritePaths=/var/lib/workshop-ventilation", text)


if __name__ == "__main__":
    unittest.main()
