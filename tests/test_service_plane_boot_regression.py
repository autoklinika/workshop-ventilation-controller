from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServicePlaneBootRegressionTests(unittest.TestCase):
    def test_heartbeat_validator_is_executable_and_checks_enabled_plus_active(self) -> None:
        path = ROOT / "tools/validate_cm5_service_heartbeat.sh"
        mode = path.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "heartbeat validator must be executable")

        source = path.read_text(encoding="utf-8")
        enabled = "systemctl is-enabled --quiet wvc-service-heartbeat.service"
        active = "systemctl is-active --quiet wvc-service-heartbeat.service"
        self.assertIn(enabled, source)
        self.assertIn(active, source)
        self.assertLess(source.index(enabled), source.index(active))
        self.assertIn("wvc-service-agent.service", source)

    def test_legacy_installer_establishes_unambiguous_durable_boot_target(self) -> None:
        source = (ROOT / "tools/install_cm5_service_heartbeat.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "systemctl disable --now wvc-service-agent.service", source
        )
        self.assertIn(
            "systemctl enable wvc-service-heartbeat.service", source
        )
        self.assertIn(
            "systemctl is-enabled --quiet wvc-service-heartbeat.service", source
        )
        self.assertIn(
            "systemctl is-active --quiet wvc-service-heartbeat.service", source
        )

    def test_production_agent_installer_and_validator_protect_boot_state(self) -> None:
        installer = (ROOT / "tools/install_cm5_service_agent.sh").read_text(
            encoding="utf-8"
        )
        validator = (ROOT / "tools/validate_cm5_service_agent.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "systemctl disable --now wvc-service-heartbeat.service", installer
        )
        self.assertIn("systemctl enable wvc-service-agent.service", installer)
        self.assertIn(
            "systemctl is-enabled --quiet wvc-service-agent.service", installer
        )
        self.assertIn(
            "systemctl is-active --quiet wvc-service-agent.service", installer
        )
        self.assertIn(
            "systemctl is-enabled --quiet wvc-service-agent.service", validator
        )
        self.assertIn(
            "systemctl is-active --quiet wvc-service-agent.service", validator
        )
        self.assertIn(
            "systemctl is-enabled --quiet wvc-service-heartbeat.service", validator
        )

    def test_general_boot_check_is_separate_from_ventilation_core(self) -> None:
        path = ROOT / "tools/validate_cm5_service_plane_boot.sh"
        self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        source = path.read_text(encoding="utf-8")
        self.assertIn("wvc-service-agent.service", source)
        self.assertIn("wvc-service-heartbeat.service", source)
        self.assertNotIn("ventilation-core.service", source)
        self.assertNotIn("ventilation_core", source)

    def test_nvme_migration_does_not_disable_service_plane_units(self) -> None:
        source = (ROOT / "tools/migrate_cm5_persistent_data_to_nvme.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            "systemctl disable --now wvc-service-heartbeat.service", source
        )
        self.assertNotIn("systemctl disable wvc-service-heartbeat.service", source)
        self.assertNotIn("systemctl disable wvc-service-agent.service", source)

    def test_changed_shell_scripts_have_valid_syntax(self) -> None:
        for relative in (
            "tools/install_cm5_service_heartbeat.sh",
            "tools/validate_cm5_service_heartbeat.sh",
            "tools/validate_cm5_service_plane_boot.sh",
            "tools/install_cm5_service_agent.sh",
            "tools/validate_cm5_service_agent.sh",
        ):
            with self.subTest(relative=relative):
                result = subprocess.run(
                    ["bash", "-n", str(ROOT / relative)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
