#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_TARGET="/usr/local/sbin/wvc-zigbee-state-backup"
SERVICE_TARGET="/etc/systemd/system/wvc-zigbee-state-backup.service"
PATH_TARGET="/etc/systemd/system/wvc-zigbee-state-backup.path"
LEGACY_TIMER_TARGET="/etc/systemd/system/wvc-zigbee-state-backup.timer"
BACKUP_ROOT="/var/backups/workshop-ventilation/zigbee2mqtt"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash tools/install_cm5_zigbee_state_backup.sh"
mountpoint -q /srv/wvc-data || fail "/srv/wvc-data is not mounted"
[[ -d /srv/wvc-data/zigbee2mqtt ]] || fail "Zigbee2MQTT data directory is missing"

install -d -m 0700 "${BACKUP_ROOT}"
install -m 0755 "${ROOT_DIR}/tools/backup_cm5_zigbee_state.sh" "${SCRIPT_TARGET}"
install -m 0644 "${ROOT_DIR}/deploy/systemd/wvc-zigbee-state-backup.service" "${SERVICE_TARGET}"
install -m 0644 "${ROOT_DIR}/deploy/systemd/wvc-zigbee-state-backup.path" "${PATH_TARGET}"

# Stage 1 used an hourly timer. Event-driven backup supersedes it.
systemctl disable --now wvc-zigbee-state-backup.timer 2>/dev/null || true
rm -f "${LEGACY_TIMER_TARGET}"

systemctl daemon-reload
systemctl reset-failed wvc-zigbee-state-backup.service 2>/dev/null || true
systemctl enable --now wvc-zigbee-state-backup.path
if ! systemctl start wvc-zigbee-state-backup.service; then
    echo "===== wvc-zigbee-state-backup.service =====" >&2
    systemctl status wvc-zigbee-state-backup.service --no-pager -l >&2 || true
    echo "===== recent journal =====" >&2
    journalctl -u wvc-zigbee-state-backup.service -n 80 --no-pager >&2 || true
    fail "Initial Zigbee state backup failed"
fi
systemctl is-active --quiet wvc-zigbee-state-backup.path || fail "Backup path watcher is not active"

LATEST="$(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'zigbee2mqtt-state-*.tar.gz' -printf '%p\n' | LC_ALL=C sort | tail -n 1)"
[[ -n "${LATEST}" ]] || fail "Initial Zigbee state backup was not created"
(cd "$(dirname "${LATEST}")" && sha256sum -c "$(basename "${LATEST}.sha256")")
tar -tzf "${LATEST}" >/dev/null

echo "WVC Zigbee state backup: PASS"
echo "Latest: ${LATEST}"
systemctl status wvc-zigbee-state-backup.path --no-pager -l
