import unittest
from pathlib import Path


UNIT = Path(__file__).resolve().parents[1] / "deploy" / "systemd" / "wvc-service-heartbeat.service"
NFT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "cm5"
    / "wifi"
    / "nftables"
    / "wvc-sensor-service.nft"
)


class ServiceHeartbeatDeploymentTest(unittest.TestCase):
    def test_receiver_is_separate_from_ventilation_core(self) -> None:
        unit = UNIT.read_text(encoding="utf-8")
        self.assertIn("ventilation_core.service_heartbeat", unit)
        self.assertNotIn("ventilation_core.main", unit)
        self.assertIn("--bind 10.55.0.1", unit)
        self.assertIn("--port 45551", unit)

    def test_only_udp_heartbeat_port_is_added_before_wlan_drop(self) -> None:
        rules = NFT.read_text(encoding="utf-8")
        heartbeat = rules.index("udp dport 45551 accept")
        drop = rules.index('iifname "wlan0" drop')
        self.assertLess(heartbeat, drop)
        self.assertNotIn("tcp dport", rules)


if __name__ == "__main__":
    unittest.main()
