#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${WVC_ZIGBEE_STATE_SOURCE:-/srv/wvc-data/zigbee2mqtt}"
DATA_MOUNT="${WVC_ZIGBEE_DATA_MOUNT:-/srv/wvc-data}"
BACKUP_ROOT="${WVC_ZIGBEE_STATE_BACKUP_ROOT:-/var/backups/workshop-ventilation/zigbee2mqtt}"
RETENTION="${WVC_ZIGBEE_STATE_BACKUP_RETENTION:-30}"
LOCK_FILE="${WVC_ZIGBEE_STATE_LOCK:-/run/wvc-zigbee-state-backup/backup.lock}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

info() {
    echo "INFO: $*"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root"
fi

[[ "${RETENTION}" =~ ^[1-9][0-9]*$ ]] || fail "Retention must be a positive integer"
mountpoint -q "${DATA_MOUNT}" || fail "${DATA_MOUNT} is not mounted"
[[ -d "${SOURCE_DIR}" ]] || fail "Zigbee2MQTT data directory missing: ${SOURCE_DIR}"

for required in configuration.yaml database.db coordinator_backup.json; do
    [[ -s "${SOURCE_DIR}/${required}" ]] || fail "Required Zigbee2MQTT state is missing or empty: ${required}"
done

python3 - "${SOURCE_DIR}/coordinator_backup.json" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    json.load(handle)
PY

install -d -m 0700 "${BACKUP_ROOT}"
install -d -m 0700 "$(dirname "${LOCK_FILE}")"
exec 9>"${LOCK_FILE}"
flock -n 9 || fail "Another Zigbee state backup is already running"

SOURCE_DEVICE_RAW="$(findmnt -n -o SOURCE -T "${SOURCE_DIR}" 2>/dev/null || true)"
BACKUP_DEVICE_RAW="$(findmnt -n -o SOURCE -T "${BACKUP_ROOT}" 2>/dev/null || true)"
ROOT_DEVICE_RAW="$(findmnt -n -o SOURCE / 2>/dev/null || true)"

normalize_source_device() {
    printf '%s\n' "$1" | sed 's/\[.*$//'
}

SOURCE_DEVICE="$(normalize_source_device "${SOURCE_DEVICE_RAW}")"
BACKUP_DEVICE="$(normalize_source_device "${BACKUP_DEVICE_RAW}")"
ROOT_DEVICE="$(normalize_source_device "${ROOT_DEVICE_RAW}")"

[[ "${SOURCE_DEVICE}" == /dev/nvme* ]] || fail "Source is not on NVMe: ${SOURCE_DEVICE:-unknown}"
[[ -n "${BACKUP_DEVICE}" ]] || fail "Cannot identify backup filesystem"
[[ "${BACKUP_DEVICE}" != "${SOURCE_DEVICE}" ]] || fail "Backup destination is on the same device as Zigbee2MQTT state"
[[ "${BACKUP_DEVICE}" == "${ROOT_DEVICE}" ]] || fail "Backup destination must be on the eMMC root filesystem (${ROOT_DEVICE}), got ${BACKUP_DEVICE}"

state_fingerprint() {
    (
        cd "${SOURCE_DIR}"
        while IFS= read -r -d '' path; do
            sha256sum "${path}"
        done < <(find . -type f ! -path './log/*' ! -name '*.log' -print0 | LC_ALL=C sort -z)
    ) | sha256sum | awk '{print $1}'
}

CURRENT_FINGERPRINT="$(state_fingerprint)"
[[ -n "${CURRENT_FINGERPRINT}" ]] || fail "Cannot calculate Zigbee state fingerprint"

LATEST_FINGERPRINT_FILE="${BACKUP_ROOT}/latest.source.sha256"
if [[ -f "${LATEST_FINGERPRINT_FILE}" ]] && [[ "$(tr -d '\r\n' < "${LATEST_FINGERPRINT_FILE}")" == "${CURRENT_FINGERPRINT}" ]]; then
    info "Zigbee2MQTT state unchanged; no new eMMC write needed"
    exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASENAME="zigbee2mqtt-state-${STAMP}"
FINAL_ARCHIVE="${BACKUP_ROOT}/${BASENAME}.tar.gz"
FINAL_SHA="${FINAL_ARCHIVE}.sha256"
FINAL_META="${FINAL_ARCHIVE}.meta"
TMP_ARCHIVE="$(mktemp "${BACKUP_ROOT}/.${BASENAME}.XXXXXX.tar.gz")"
TMP_SHA="${TMP_ARCHIVE}.sha256"
TMP_META="${TMP_ARCHIVE}.meta"
TMP_LATEST="${BACKUP_ROOT}/.latest.source.sha256.$$"

cleanup() {
    rm -f "${TMP_ARCHIVE}" "${TMP_SHA}" "${TMP_META}" "${TMP_LATEST}"
}
trap cleanup EXIT

CONSISTENT=0
for attempt in 1 2 3; do
    BEFORE="$(state_fingerprint)"
    rm -f "${TMP_ARCHIVE}"
    tar \
        --exclude='./log' \
        --exclude='./log/*' \
        --exclude='*.log' \
        -C "${SOURCE_DIR}" \
        -czf "${TMP_ARCHIVE}" .
    AFTER="$(state_fingerprint)"
    if [[ "${BEFORE}" == "${AFTER}" ]]; then
        CURRENT_FINGERPRINT="${AFTER}"
        CONSISTENT=1
        break
    fi
    info "Zigbee2MQTT state changed during snapshot attempt ${attempt}; retrying"
    sleep 1
done
[[ "${CONSISTENT}" -eq 1 ]] || fail "Could not obtain a consistent Zigbee2MQTT snapshot after 3 attempts"

for required in ./configuration.yaml ./database.db ./coordinator_backup.json; do
    tar -tzf "${TMP_ARCHIVE}" | grep -Fx "${required}" >/dev/null || fail "Snapshot does not contain ${required}"
done

tar -tzf "${TMP_ARCHIVE}" >/dev/null
ARCHIVE_SHA256="$(sha256sum "${TMP_ARCHIVE}" | awk '{print $1}')"
printf '%s  %s\n' "${ARCHIVE_SHA256}" "${BASENAME}.tar.gz" > "${TMP_SHA}"

REPO_SHA="unknown"
if [[ -d /home/wentylacja/workshop-ventilation-controller/.git ]]; then
    REPO_SHA="$(git -C /home/wentylacja/workshop-ventilation-controller rev-parse HEAD 2>/dev/null || echo unknown)"
fi

cat > "${TMP_META}" <<META
WVC Zigbee2MQTT state backup
created_utc=${STAMP}
source=${SOURCE_DIR}
source_device=${SOURCE_DEVICE}
source_device_raw=${SOURCE_DEVICE_RAW}
backup_root=${BACKUP_ROOT}
backup_device=${BACKUP_DEVICE}
backup_device_raw=${BACKUP_DEVICE_RAW}
source_fingerprint_sha256=${CURRENT_FINGERPRINT}
archive_sha256=${ARCHIVE_SHA256}
repository_sha=${REPO_SHA}
hostname=$(hostname)
META

chmod 0600 "${TMP_ARCHIVE}" "${TMP_SHA}" "${TMP_META}"
mv "${TMP_ARCHIVE}" "${FINAL_ARCHIVE}"
mv "${TMP_SHA}" "${FINAL_SHA}"
mv "${TMP_META}" "${FINAL_META}"
printf '%s\n' "${CURRENT_FINGERPRINT}" > "${TMP_LATEST}"
chmod 0600 "${TMP_LATEST}"
mv "${TMP_LATEST}" "${LATEST_FINGERPRINT_FILE}"

mapfile -t ARCHIVES < <(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'zigbee2mqtt-state-*.tar.gz' -printf '%f\n' | LC_ALL=C sort)
if (( ${#ARCHIVES[@]} > RETENTION )); then
    REMOVE_COUNT=$(( ${#ARCHIVES[@]} - RETENTION ))
    for ((i = 0; i < REMOVE_COUNT; i++)); do
        old="${BACKUP_ROOT}/${ARCHIVES[$i]}"
        rm -f "${old}" "${old}.sha256" "${old}.meta"
    done
fi

trap - EXIT
info "Backup created: ${FINAL_ARCHIVE}"
info "SHA256: ${ARCHIVE_SHA256}"
info "State fingerprint: ${CURRENT_FINGERPRINT}"
