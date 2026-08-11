import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_WIFI = (
    ROOT
    / "firmware"
    / "sensor-node"
    / "components"
    / "service_wifi"
    / "src"
    / "service_wifi.cpp"
)
CREDENTIALS_HEADER = (
    ROOT
    / "firmware"
    / "sensor-node"
    / "components"
    / "config"
    / "include"
    / "config"
    / "service_credentials.hpp"
)
CREDENTIALS_SOURCE = (
    ROOT
    / "firmware"
    / "sensor-node"
    / "components"
    / "config"
    / "src"
    / "service_credentials.cpp"
)
PROVISIONER = ROOT / "tools" / "provision_sensor_node_service.py"
WIFI_INSTALLER = ROOT / "tools" / "install_cm5_wifi_service.sh"
WIFI_VALIDATOR = ROOT / "tools" / "validate_cm5_wifi_service.sh"
HEARTBEAT_INSTALLER = ROOT / "tools" / "install_cm5_service_heartbeat.sh"


class ServiceWifiOpenNetworkTest(unittest.TestCase):
    def test_firmware_uses_open_auth_without_psk(self) -> None:
        wifi = FIRMWARE_WIFI.read_text(encoding="utf-8")
        header = CREDENTIALS_HEADER.read_text(encoding="utf-8")
        source = CREDENTIALS_SOURCE.read_text(encoding="utf-8")

        self.assertIn("WIFI_AUTH_OPEN", wifi)
        self.assertNotIn("WIFI_AUTH_WPA2_PSK", wifi)
        self.assertNotIn("wifi_config.sta.password", wifi)
        self.assertNotIn("wifi_psk", header)
        self.assertNotIn("wifi_psk", source)

    def test_provisioner_does_not_request_or_write_wifi_password(self) -> None:
        provisioner = PROVISIONER.read_text(encoding="utf-8")

        self.assertNotIn("getpass", provisioner)
        self.assertNotIn("wifi_psk", provisioner)
        self.assertNotIn("WPA2 PSK", provisioner)
        self.assertIn("auth_key", provisioner)
        self.assertIn("HMAC-SHA256", provisioner)

    def test_cm5_installer_removes_legacy_security_setting(self) -> None:
        installer = WIFI_INSTALLER.read_text(encoding="utf-8")

        self.assertIn("remove 802-11-wireless-security", installer)
        self.assertNotIn("key-mgmt wpa-psk", installer)
        self.assertNotIn("WPA2 key", installer)

    def test_validator_accepts_networkmanager_symbolic_power_save_value(self) -> None:
        validator = WIFI_VALIDATOR.read_text(encoding="utf-8")

        self.assertIn("2|disable", validator)
        self.assertIn("service AP has no layer-2 authentication", validator)

    def test_key_registry_install_restarts_receiver(self) -> None:
        installer = HEARTBEAT_INSTALLER.read_text(encoding="utf-8")

        self.assertIn("systemctl restart wvc-service-heartbeat.service", installer)
        self.assertNotIn("enable --now wvc-service-heartbeat.service", installer)


if __name__ == "__main__":
    unittest.main()
