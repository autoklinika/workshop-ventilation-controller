from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_dfr0473_power_domain_cm5.sh"


class Dfr0473PowerDomainCm5ValidationTest(unittest.TestCase):
    def test_harness_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_harness_never_powers_off_or_reboots_host(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")

        forbidden = (
            "systemctl poweroff",
            "systemctl reboot",
            "shutdown -h",
            "shutdown -r",
            "reboot -f",
            "poweroff -f",
        )
        for command in forbidden:
            with self.subTest(command=command):
                self.assertNotIn(command, source)

    def test_harness_requires_stage14_and_safe_local_zero_before_service_changes(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")

        self.assertIn('EXPECTED_BRANCH="agent/power-domain-dfr0473-stage14"', source)
        stop_at = source.index("ventilation_core.ctl stop")
        install_at = source.index("INSTALL STAGE14 UNITS")
        self.assertLess(stop_at, install_at)
        self.assertIn('s.get("mode") != "STOP"', source)
        self.assertIn('sp.get("supply_voltage") != 0.0', source)
        self.assertIn('sp.get("extract_voltage") != 0.0', source)
        self.assertIn('s.get("output_state_known") is not True', source)

    def test_stop_failure_is_diagnostic_and_cannot_reach_install_or_relay_changes(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")

        self.assertIn("STOP FAILURE DIAGNOSTICS", source)
        self.assertIn("raw STOP response:", source)
        self.assertIn("current core status:", source)
        self.assertIn("recent ventilation-core journal:", source)
        self.assertIn("no service configuration or relay state was changed", source)
        failure_guard_at = source.index('if [ "$STOP_RC" -ne 0 ]')
        install_at = source.index("INSTALL STAGE14 UNITS")
        relay_test_at = source.index("CONTROLLED POWER-DOMAIN OFF TEST")
        self.assertLess(failure_guard_at, install_at)
        self.assertLess(failure_guard_at, relay_test_at)

    def test_harness_physically_checks_off_then_on_and_core_returns_safe(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")

        self.assertIn("PHYSICAL CHECK 1", source)
        self.assertIn("PHYSICAL CHECK 2", source)
        self.assertIn("sudo systemctl stop wvc-host-power.service", source)
        self.assertIn("sudo systemctl start ventilation-core.service", source)
        self.assertIn("post-start STOP / 0 V: PASS", source)


if __name__ == "__main__":
    unittest.main()
