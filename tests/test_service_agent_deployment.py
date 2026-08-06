from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServiceAgentDeploymentTests(unittest.TestCase):
    def test_unit_is_hardened_and_keeps_service_plane_independent(self) -> None:
        unit = (ROOT / "deploy/systemd/wvc-service-agent.service").read_text(encoding="utf-8")

        self.assertIn("ExecStart=/usr/bin/python3 -m ventilation_core.service_agent", unit)
        self.assertIn("RuntimeDirectory=wvc-service-agent", unit)
        self.assertIn("StateDirectory=wvc-service-heartbeat", unit)
        self.assertIn("RestrictAddressFamilies=AF_INET AF_UNIX", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("Conflicts=wvc-service-heartbeat.service", unit)
        self.assertNotIn("ventilation-core.service", unit)

    def test_installer_replaces_legacy_receiver_without_touching_ventilation_core(self) -> None:
        installer = (ROOT / "tools/install_cm5_service_agent.sh").read_text(encoding="utf-8")

        self.assertIn("systemctl disable --now wvc-service-heartbeat.service", installer)
        self.assertIn("systemctl enable wvc-service-agent.service", installer)
        self.assertIn("systemctl restart wvc-service-agent.service", installer)
        self.assertIn("/var/lib/wvc-service-heartbeat", installer)
        self.assertIn("/run/wvc-service-agent/service-agent.sock", installer)
        self.assertIn("Service agent API did not become ready", installer)
        self.assertNotIn("systemctl restart ventilation-core", installer)
        self.assertNotIn("systemctl stop ventilation-core", installer)

    def test_validator_checks_socket_udp_firewall_and_isolation(self) -> None:
        validator = (ROOT / "tools/validate_cm5_service_agent.sh").read_text(encoding="utf-8")

        self.assertIn("wvc-service-agent.service", validator)
        self.assertIn("/run/wvc-service-agent/service-agent.sock", validator)
        self.assertIn("10.55.0.1:45551", validator)
        self.assertIn("udp dport 45551 accept", validator)
        self.assertIn("net.ipv4.ip_forward", validator)
        self.assertIn("net.ipv6.conf.all.forwarding", validator)
        self.assertIn("ventilation_core.service_ctl status", validator)

    def test_soak_validator_checks_agent_sensor_bus_and_core_pid(self) -> None:
        validator = (ROOT / "tools/validate_cm5_service_agent_soak.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("DURATION_SECONDS=", validator)
        self.assertIn("INTERVAL_SECONDS=", validator)
        self.assertIn("ventilation_core.service_ctl status", validator)
        self.assertIn("ventilation_core.ctl sensors", validator)
        self.assertIn("worker_restarts", validator)
        self.assertIn("communication_errors", validator)
        self.assertIn("polls did not increase", validator)
        self.assertIn("ventilation-core PID changed", validator)
        self.assertIn("validate_cm5_service_agent.sh", validator)
        self.assertNotIn("systemctl restart ventilation-core", validator)
        self.assertNotIn("systemctl stop ventilation-core", validator)

    def test_soak_validator_uses_fault_injection_counters_as_baseline(self) -> None:
        soak = (ROOT / "tools/validate_cm5_service_agent_soak.sh").read_text(encoding="utf-8")

        self.assertIn("historical SENSOR BUS counters accepted as soak baseline", soak)
        self.assertIn("acquired a non-successful poll during soak", soak)
        self.assertIn("counter {field} changed", soak)
        self.assertIn("invalid_measurements", soak)
        self.assertIn("stale_measurements", soak)
        self.assertIn("map_version_errors", soak)
        self.assertNotIn('if node.get("communication_errors") != 0', soak)
        self.assertNotIn('if node.get("polls") != node.get("successful_polls")', soak)

    def test_soak_validator_preserves_and_explains_failure_diagnostics(self) -> None:
        soak = (ROOT / "tools/validate_cm5_service_agent_soak.sh").read_text(encoding="utf-8")

        self.assertIn("Soak diagnostics preserved in", soak)
        self.assertIn("not all service nodes are online:", soak)
        self.assertIn("boot_id", soak)
        self.assertIn("received_unix_ms", soak)
        self.assertIn("iw dev wlan0 station dump", soak)
        self.assertIn("service-agent-journal.txt", soak)
        self.assertIn("collect_failure_diagnostics", soak)
        self.assertIn("Current SENSOR BUS snapshot", soak)
        self.assertIn("/var/lib/misc/dnsmasq-wvc.leases", soak)

    def test_dropout_collector_captures_service_wifi_and_modbus_context(self) -> None:
        diagnostic = (ROOT / "tools/diagnose_cm5_service_agent_dropout.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("ventilation_core.service_ctl status", diagnostic)
        self.assertIn("ventilation_core.ctl sensors", diagnostic)
        self.assertIn("journalctl -u wvc-service-agent.service", diagnostic)
        self.assertIn("iw dev wlan0 station dump", diagnostic)
        self.assertIn("brcmfmac", diagnostic)
        self.assertIn("boot_id", diagnostic)
        self.assertIn("modbus_requests_total", diagnostic)

    def test_agent_does_not_import_control_or_sensor_bus_components(self) -> None:
        agent = (ROOT / "src/ventilation_core/service_agent.py").read_text(encoding="utf-8")

        self.assertNotIn("sensor_bus_worker", agent)
        self.assertNotIn("process_actuator", agent)
        self.assertNotIn("FanSetpointPolicy", agent)
        self.assertNotIn("ventilation_core.main", agent)


if __name__ == "__main__":
    unittest.main()
