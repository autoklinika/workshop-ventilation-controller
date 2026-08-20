from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NvmeDataTierDeploymentTest(unittest.TestCase):
    def test_prepare_script_is_dry_run_by_default_and_refuses_root_disk(self) -> None:
        text = (ROOT / "tools/prepare_cm5_nvme_data_disk.sh").read_text(encoding="utf-8")
        self.assertIn("APPLY=0", text)
        self.assertIn("--apply", text)
        self.assertIn("REFUSING: selected device backs the root filesystem", text)
        self.assertIn("mkfs.ext4", text)
        self.assertIn('LABEL="WVC_DATA"', text)
        self.assertIn("/srv/wvc-data", text)
        self.assertIn("defaults,noatime,nofail,x-systemd.device-timeout=10s", text)
        self.assertIn("fstrim.timer", text)

    def test_migration_keeps_low_churn_control_configuration_on_emmc(self) -> None:
        text = (ROOT / "tools/migrate_cm5_persistent_data_to_nvme.sh").read_text(encoding="utf-8")
        self.assertIn("telemetry.sqlite3", text)
        self.assertIn("alerts.sqlite3", text)
        self.assertIn("/var/lib/wvc-service-heartbeat", text)
        self.assertIn("/var/lib/zigbee2mqtt", text)
        self.assertNotIn('copy_if_exists "/var/lib/workshop-ventilation/automation.sqlite3"', text)
        self.assertNotIn('copy_if_exists "/var/lib/workshop-ventilation/zigbee-roles.json"', text)
        self.assertIn("safe baseline: STOP / 0 V", text)
        self.assertIn("Legacy eMMC files were intentionally retained", text)

    def test_migration_repairs_existing_webui_environment_overrides(self) -> None:
        text = (ROOT / "tools/migrate_cm5_persistent_data_to_nvme.sh").read_text(encoding="utf-8")
        self.assertIn('WEB_ENV_FILE="/etc/default/wvc-web-ui"', text)
        self.assertIn('WEB_ENV_BACKUP="/etc/default/wvc-web-ui.pre-nvme-migration.bak"', text)
        self.assertIn("upsert_env_value()", text)
        self.assertIn('cp -a "$WEB_ENV_FILE" "$WEB_ENV_BACKUP"', text)
        for key, suffix in (
            ("WVC_WEB_TELEMETRY_DATABASE", "telemetry.sqlite3"),
            ("WVC_WEB_ALERT_DATABASE", "alerts.sqlite3"),
            ("WVC_WEB_WEATHER_SNAPSHOT", "weather.json"),
            ("WVC_WEB_AI_ADVISORY_CACHE", "ai-advisory.json"),
        ):
            self.assertIn(
                f'upsert_env_value "$WEB_ENV_FILE" "{key}" '
                f'"$DATA_ROOT/workshop-ventilation/{suffix}"',
                text,
            )

    def test_validator_checks_webui_override_and_effective_process_environment(self) -> None:
        text = (ROOT / "tools/validate_cm5_nvme_data.sh").read_text(encoding="utf-8")
        self.assertIn('WEB_ENV_FILE="/etc/default/wvc-web-ui"', text)
        self.assertIn("check_env_file_value()", text)
        self.assertIn("check_process_env_value()", text)
        self.assertIn('WEB_PID="$(systemctl show -p MainPID --value wvc-web-ui.service', text)
        self.assertIn('tr \'\\0\' \'\\n\' <"/proc/$WEB_PID/environ"', text)
        for key in (
            "WVC_WEB_TELEMETRY_DATABASE",
            "WVC_WEB_ALERT_DATABASE",
            "WVC_WEB_WEATHER_SNAPSHOT",
            "WVC_WEB_AI_ADVISORY_CACHE",
        ):
            self.assertIn(key, text)

    def test_writer_units_fail_closed_when_nvme_mount_is_missing(self) -> None:
        for name in (
            "wvc-telemetry-sync.service",
            "wvc-ai-advisory.service",
            "wvc-weather.service",
            "wvc-service-agent.service",
            "wvc-service-heartbeat.service",
            "zigbee2mqtt.service",
        ):
            with self.subTest(unit=name):
                text = (ROOT / "deploy/systemd" / name).read_text(encoding="utf-8")
                self.assertIn("RequiresMountsFor=/srv/wvc-data", text)
                self.assertIn("ExecStartPre=/usr/bin/mountpoint -q /srv/wvc-data", text)

    def test_core_is_not_hard_dependent_on_nvme(self) -> None:
        text = (ROOT / "deploy/systemd/ventilation-core.service").read_text(encoding="utf-8")
        self.assertNotIn("RequiresMountsFor=/srv/wvc-data", text)
        self.assertIn("WVC_ALERT_STORE_ALLOW_VOLATILE_FALLBACK=1", text)
        self.assertIn("--alerts-db /srv/wvc-data/workshop-ventilation/alerts.sqlite3", text)
        self.assertIn("--automation-db /var/lib/workshop-ventilation/automation.sqlite3", text)
        self.assertIn("--zigbee-roles-file /var/lib/workshop-ventilation/zigbee-roles.json", text)

    def test_os_logging_and_mqtt_do_not_create_persistent_emmc_churn(self) -> None:
        journal = (ROOT / "deploy/cm5/storage/90-wvc-emmc-protection.conf").read_text(encoding="utf-8")
        mqtt = (ROOT / "deploy/cm5/zigbee/mosquitto/wvc-zigbee-local.conf").read_text(encoding="utf-8")
        self.assertIn("Storage=volatile", journal)
        self.assertIn("RuntimeMaxUse=64M", journal)
        self.assertIn("persistence false", mqtt)


if __name__ == "__main__":
    unittest.main()
