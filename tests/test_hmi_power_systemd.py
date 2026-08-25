from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy/systemd/wvc-hmi-power.service"


class HmiPowerSystemdTest(unittest.TestCase):
    def test_unit_uses_wake_on_start_and_sleep_on_stop(self) -> None:
        text = UNIT.read_text(encoding="utf-8")
        self.assertIn("ventilation_core.hmi_power wake", text)
        self.assertIn("ventilation_core.hmi_power sleep", text)
        self.assertIn("RemainAfterExit=yes", text)
        self.assertIn("WantedBy=multi-user.target", text)

    def test_hmi_target_is_runtime_configured(self) -> None:
        text = UNIT.read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=/etc/workshop-ventilation/hmi-power.env", text)
        self.assertIn("--target ${WVC_HMI_ADB_TARGET}", text)
        self.assertNotIn("Environment=WVC_HMI_ADB_TARGET=192.168.1.39:5555", text)

    def test_hmi_is_network_capable_but_not_a_safety_dependency(self) -> None:
        text = UNIT.read_text(encoding="utf-8")
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", text)
        self.assertNotIn("Requires=wvc-host-power.service", text)
        self.assertNotIn("Requires=ventilation-core.service", text)
        self.assertNotIn("Before=wvc-host-power.service", text)
        self.assertNotIn("Before=ventilation-core.service", text)

    def test_shutdown_timeout_is_bounded(self) -> None:
        text = UNIT.read_text(encoding="utf-8")
        self.assertIn("TimeoutStopSec=8", text)
        self.assertIn("--timeout 1.5 --attempts 2 --retry-delay 0.5", text)


if __name__ == "__main__":
    unittest.main()
