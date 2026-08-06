from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServiceOtaDeploymentTests(unittest.TestCase):
    def test_firmware_exposes_authenticated_streaming_ota(self) -> None:
        source = (
            ROOT
            / "firmware/sensor-node/components/service_ota/src/service_ota.cpp"
        ).read_text(encoding="utf-8")
        for fragment in (
            '"/v1/ota/challenge"',
            '"/v1/ota/status"',
            '"/v1/ota/image"',
            "calculate_hmac",
            "constant_time_equal",
            "esp_ota_get_next_update_partition",
            "esp_ota_begin",
            "esp_ota_write",
            "esp_ota_abort",
            "esp_ota_end",
            "esp_ota_set_boot_partition",
            "mbedtls_sha256_update",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)

    def test_cm5_uses_background_worker_and_local_commands(self) -> None:
        agent = (ROOT / "src/ventilation_core/service_agent_ota.py").read_text(
            encoding="utf-8"
        )
        coordinator = (ROOT / "src/ventilation_core/service_ota.py").read_text(
            encoding="utf-8"
        )
        ctl = (ROOT / "src/ventilation_core/service_ctl.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("threading.Thread", coordinator)
        self.assertIn('command not in {"ota-install", "ota-status"}', agent)
        self.assertIn('subparsers.add_parser("ota-install")', ctl)
        self.assertIn('subparsers.add_parser("ota-status")', ctl)
        self.assertNotIn("ventilation_core.application", agent)
        self.assertNotIn("sensor_bus", agent)

    def test_firewall_allows_only_established_ota_replies(self) -> None:
        nft = (
            ROOT / "deploy/cm5/wifi/nftables/wvc-sensor-service.nft"
        ).read_text(encoding="utf-8")
        self.assertIn('iifname "wlan0" ct state established,related accept', nft)
        self.assertNotIn("tcp dport 45552", nft)
        self.assertIn('iifname "wlan0" drop', nft)

    def test_systemd_runs_ota_capable_agent(self) -> None:
        unit = (
            ROOT / "deploy/systemd/wvc-service-agent.service"
        ).read_text(encoding="utf-8")
        self.assertIn("-m ventilation_core.service_agent_ota", unit)
        self.assertIn("RestrictAddressFamilies=AF_INET AF_UNIX", unit)
        self.assertIn("StateDirectory=wvc-service-heartbeat", unit)

    def test_workflow_uploads_bootstrap_artifact(self) -> None:
        workflow = (
            ROOT / ".github/workflows/sensor-node-firmware.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("kamod-service-ota-bootstrap", workflow)
        self.assertIn("build/flasher_args.json", workflow)


if __name__ == "__main__":
    unittest.main()
