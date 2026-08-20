import unittest
from pathlib import Path


UNIT_PATH = Path(__file__).resolve().parents[1] / "deploy" / "systemd" / "wvc-telemetry-sync.service"


class TelemetrySystemdUnitTest(unittest.TestCase):
    def test_telemetry_service_does_not_require_core(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("After=ventilation-core.service", unit)
        self.assertNotIn("Requires=ventilation-core.service", unit)

    def test_telemetry_service_runs_as_ventilation_user(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("User=wentylacja", unit)
        self.assertIn("Group=wentylacja", unit)

    def test_telemetry_service_uses_fail_closed_nvme_data_tier(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn("RequiresMountsFor=/srv/wvc-data", unit)
        self.assertIn("ExecStartPre=/usr/bin/mountpoint -q /srv/wvc-data", unit)
        self.assertIn("/srv/wvc-data/workshop-ventilation/telemetry.sqlite3", unit)
        self.assertNotIn("--database /var/lib/workshop-ventilation/telemetry.sqlite3", unit)

    def test_remote_sink_environment_file_is_optional(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=-/etc/default/wvc-telemetry-sync", unit)


if __name__ == "__main__":
    unittest.main()
