from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_cm5_service_wifi_channel_ab.sh"


class ServiceWifiChannelAbTests(unittest.TestCase):
    def test_script_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_ab_test_is_pinned_to_channels_6_and_11_and_restores_6(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('BASE_CHANNEL="6"', source)
        self.assertIn('TEST_CHANNEL="11"', source)
        self.assertIn("restore_channel6()", source)
        self.assertIn("trap cleanup EXIT INT TERM", source)
        self.assertIn('run_phase "A" "$BASE_CHANNEL"', source)
        self.assertIn('run_phase "B" "$TEST_CHANNEL"', source)
        self.assertIn("restore_channel6", source)

    def test_helper_changes_only_service_wifi_runtime_and_collects_both_nodes(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('PROFILE="wvc-sensor-service"', source)
        self.assertIn('IFACE="wlan0"', source)
        self.assertIn('nmcli connection modify "$PROFILE" 802-11-wireless.channel', source)
        self.assertIn('systemctl restart wvc-sensor-firewall.service', source)
        self.assertIn('systemctl restart wvc-sensor-dhcp.service', source)
        self.assertIn('"sensor-node-1"', source)
        self.assertIn('"sensor-node-2"', source)
        self.assertIn('"sequence_gap_events"', source)
        self.assertIn('"missing_heartbeats_total"', source)
        self.assertIn('"heartbeat_send_failures"', source)
        self.assertIn('"wifi_disconnect_events"', source)
        self.assertNotIn("ventilation-core.service", source)
        self.assertNotIn("modbus", source.lower())


if __name__ == "__main__":
    unittest.main()
