from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EmmcWriteHardeningStage2Tests(unittest.TestCase):
    def test_dhcp_leases_are_volatile(self) -> None:
        config = (
            ROOT / "deploy/cm5/wifi/dnsmasq/wvc-sensor-service.conf"
        ).read_text(encoding="utf-8")
        unit = (
            ROOT / "deploy/cm5/wifi/systemd/wvc-sensor-dhcp.service"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "dhcp-leasefile=/run/wvc-sensor-service/dnsmasq-wvc.leases",
            config,
        )
        self.assertNotIn(
            "dhcp-leasefile=/var/lib/misc/dnsmasq-wvc.leases",
            config,
        )
        self.assertIn("RuntimeDirectory=wvc-sensor-service", unit)
        self.assertIn("RuntimeDirectoryMode=0755", unit)

    def test_ota_agent_reads_the_same_volatile_lease_table(self) -> None:
        source = (ROOT / "src/ventilation_core/service_agent_ota.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'RUNTIME_LEASES_PATH = Path("/run/wvc-sensor-service/dnsmasq-wvc.leases")',
            source,
        )
        self.assertIn("leases_path=RUNTIME_LEASES_PATH", source)

    def test_wifi_installer_keeps_only_compatibility_symlink_on_emmc(self) -> None:
        installer = (ROOT / "tools/install_cm5_wifi_service.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("rm -f /var/lib/misc/dnsmasq-wvc.leases", installer)
        self.assertIn(
            "ln -s /run/wvc-sensor-service/dnsmasq-wvc.leases",
            installer,
        )

    def test_stage2_apply_does_not_restart_ventilation_core(self) -> None:
        script = (
            ROOT / "tools/apply_cm5_emmc_write_hardening_stage2.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('VSCODE_TARGET="$DATA_ROOT/development/vscode-server"', script)
        self.assertIn("systemctl restart wvc-sensor-dhcp.service", script)
        self.assertIn("systemctl restart wvc-service-agent.service", script)
        self.assertNotIn("systemctl restart ventilation-core.service", script)
        self.assertNotIn("systemctl stop ventilation-core.service", script)
        self.assertIn(".vscode-server.emmc-rollback-", script)

    def test_stage2_validator_checks_ram_nvme_and_core_availability(self) -> None:
        validator = (
            ROOT / "tools/validate_cm5_emmc_write_hardening_stage2.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("/run is tmpfs", validator)
        self.assertIn("VS Code Server data is backed by NVMe", validator)
        self.assertIn("ventilation-core.service", validator)
        self.assertIn("journald persistent churn is disabled", validator)

    def test_repeatable_runtime_audit_is_read_only(self) -> None:
        audit = (ROOT / "tools/audit_cm5_emmc_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MMCBLK0 PHYSICAL WRITES", audit)
        self.assertIn("PROCESS WRITE_BYTES DELTA", audit)
        self.assertIn("short-window daily extrapolation is diagnostic only", audit)
        self.assertIn("audit started within 30 minutes of boot", audit)
        self.assertNotIn("unlink(", audit)
        self.assertNotIn("write_text(", audit)

    def test_stage2_cleanup_preserves_low_write_core_configuration(self) -> None:
        cleanup_path = ROOT / "tools/cleanup_cm5_emmc_rollback_stage2.sh"
        cleanup = cleanup_path.read_text(encoding="utf-8")
        self.assertIn(
            'ARCHIVE_ROOT="$DATA_ROOT/rollback/emmc-stage1-20260820"',
            cleanup,
        )
        self.assertIn("cmp -s", cleanup)
        self.assertIn("diff -qr", cleanup)
        self.assertIn("SHA256SUMS", cleanup)
        self.assertIn("automation.sqlite3", cleanup)
        self.assertIn("zigbee-roles.json", cleanup)
        self.assertNotIn("systemctl restart ventilation-core.service", cleanup)
        self.assertNotIn("systemctl stop ventilation-core.service", cleanup)

    def test_stage2_cleanup_has_valid_bash_syntax(self) -> None:
        cleanup_path = ROOT / "tools/cleanup_cm5_emmc_rollback_stage2.sh"
        result = subprocess.run(
            ["bash", "-n", str(cleanup_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
