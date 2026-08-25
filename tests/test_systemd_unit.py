import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT_PATH = ROOT / "deploy" / "systemd" / "ventilation-core.service"
HOST_POWER_UNIT_PATH = ROOT / "deploy" / "systemd" / "wvc-host-power.service"
POWER_BUTTON_CONF_PATH = (
    ROOT / "deploy" / "systemd" / "logind.conf.d" / "50-wvc-power-button.conf"
)


class SystemdUnitTest(unittest.TestCase):
    def test_supervised_workers_receive_graceful_shutdown_from_parent(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("KillSignal=SIGTERM", unit)
        self.assertIn("KillMode=mixed", unit)

    def test_stop_timeout_covers_orderly_worker_cleanup(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        timeout_line = next(
            line for line in unit.splitlines() if line.startswith("TimeoutStopSec=")
        )
        timeout_seconds = int(timeout_line.partition("=")[2])

        self.assertGreaterEqual(timeout_seconds, 20)

    def test_aero_bus_is_explicitly_configured_read_only_runtime(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("--aero-port /dev/ttyAMA4", unit)
        self.assertIn("--aero-address 44", unit)
        self.assertIn("--aero-baud 9600", unit)
        self.assertIn("--aero-inter-register-delay 0.050", unit)
        self.assertNotIn("--aero-write", unit)

    def test_both_tacho_channels_are_explicitly_enabled(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("--enable-supply-tacho", unit)
        self.assertIn("--supply-tacho-line GPIO17", unit)
        self.assertIn("--enable-extract-tacho", unit)
        self.assertIn("--extract-tacho-line GPIO27", unit)
        self.assertIn("--tacho-chip /dev/gpiochip0", unit)

    def test_core_waits_for_12v_power_domain_service_readiness(self) -> None:
        core_unit = UNIT_PATH.read_text(encoding="utf-8")
        power_unit = HOST_POWER_UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("Requires=wvc-host-power.service", core_unit)
        self.assertIn("After=local-fs.target wvc-host-power.service", core_unit)
        self.assertIn("Before=ventilation-core.service", power_unit)
        self.assertIn("Type=notify", power_unit)
        self.assertIn("NotifyAccess=main", power_unit)

    def test_host_power_owns_dfr0473_on_gpio22(self) -> None:
        unit = HOST_POWER_UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("--power-domain-chip /dev/gpiochip0", unit)
        self.assertIn("--power-domain-line GPIO22", unit)
        self.assertIn("--power-domain-stabilization 1.0", unit)

    def test_short_power_button_is_ignored_by_logind(self) -> None:
        config = POWER_BUTTON_CONF_PATH.read_text(encoding="utf-8")

        self.assertIn("HandlePowerKey=ignore", config)
        self.assertIn("HandlePowerKeyLongPress=ignore", config)


if __name__ == "__main__":
    unittest.main()
