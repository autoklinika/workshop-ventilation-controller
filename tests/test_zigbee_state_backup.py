from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ZigbeeStateBackupDeploymentTest(unittest.TestCase):
    def test_backup_is_nvme_to_emmc_only_and_change_aware(self) -> None:
        text = (ROOT / "tools/backup_cm5_zigbee_state.sh").read_text(encoding="utf-8")
        self.assertIn('/srv/wvc-data/zigbee2mqtt', text)
        self.assertIn('/var/backups/workshop-ventilation/zigbee2mqtt', text)
        self.assertIn('SOURCE_DEVICE', text)
        self.assertIn('BACKUP_DEVICE', text)
        self.assertIn('ROOT_DEVICE', text)
        self.assertIn('normalize_source_device()', text)
        self.assertIn("sed 's/\\[.*$//'", text)
        self.assertIn('SOURCE_DEVICE_RAW', text)
        self.assertIn('BACKUP_DEVICE_RAW', text)
        self.assertIn('Source is not on NVMe', text)
        self.assertIn('Backup destination is on the same device', text)
        self.assertIn('state unchanged; no new eMMC write needed', text)
        self.assertIn('WVC_ZIGBEE_STATE_BACKUP_RETENTION:-30', text)

    def test_backup_requires_critical_zigbee_state_and_validates_archive(self) -> None:
        text = (ROOT / "tools/backup_cm5_zigbee_state.sh").read_text(encoding="utf-8")
        for name in ('configuration.yaml', 'database.db', 'coordinator_backup.json'):
            self.assertIn(name, text)
        self.assertIn('json.load(handle)', text)
        self.assertIn('tar -tzf', text)
        self.assertIn('sha256sum', text)
        self.assertIn('source_fingerprint_sha256', text)
        self.assertIn("--exclude='./log'", text)
        self.assertNotIn('grep -Fxq', text)
        self.assertIn('grep -Fx "${required}" >/dev/null', text)

    def test_snapshot_retries_if_state_changes_during_copy(self) -> None:
        text = (ROOT / "tools/backup_cm5_zigbee_state.sh").read_text(encoding="utf-8")
        self.assertIn('for attempt in 1 2 3', text)
        self.assertIn('BEFORE="$(state_fingerprint)"', text)
        self.assertIn('AFTER="$(state_fingerprint)"', text)
        self.assertIn('Could not obtain a consistent Zigbee2MQTT snapshot after 3 attempts', text)

    def test_timer_is_hourly_but_backup_only_writes_on_change(self) -> None:
        timer = (ROOT / "deploy/systemd/wvc-zigbee-state-backup.timer").read_text(encoding="utf-8")
        service = (ROOT / "deploy/systemd/wvc-zigbee-state-backup.service").read_text(encoding="utf-8")
        self.assertIn('OnCalendar=hourly', timer)
        self.assertIn('Persistent=true', timer)
        self.assertIn('RandomizedDelaySec=5m', timer)
        self.assertIn('RequiresMountsFor=/srv/wvc-data', service)
        self.assertIn('ReadOnlyPaths=/srv/wvc-data/zigbee2mqtt', service)
        self.assertIn('ReadWritePaths=/var/backups/workshop-ventilation/zigbee2mqtt', service)
        self.assertIn('UMask=0077', service)

    def test_installer_creates_and_verifies_initial_snapshot(self) -> None:
        text = (ROOT / "tools/install_cm5_zigbee_state_backup.sh").read_text(encoding="utf-8")
        self.assertIn('systemctl enable --now wvc-zigbee-state-backup.timer', text)
        self.assertIn('systemctl start wvc-zigbee-state-backup.service', text)
        self.assertIn('journalctl -u wvc-zigbee-state-backup.service -n 80 --no-pager', text)
        self.assertIn('Initial Zigbee state backup failed', text)
        self.assertIn('sha256sum -c', text)
        self.assertIn('tar -tzf', text)
        self.assertIn('Initial Zigbee state backup was not created', text)


if __name__ == "__main__":
    unittest.main()
