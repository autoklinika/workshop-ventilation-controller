#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="/var/lib/zigbee2mqtt"
CONFIG_FILE="${DATA_DIR}/configuration.yaml"
ZSTACK_TEMPLATE="${ROOT_DIR}/deploy/cm5/zigbee/zigbee2mqtt/configuration.zstack-probe.yaml"
SERIAL_BY_ID="/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_822f54682ed0f01198f6423758f97c40-if00-port0"
BACKUP_FILE="${DATA_DIR}/configuration.autodetect-generated-failed.yaml"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/recover_cm5_zigbee_autodetect_probe.sh"
fi

section "QUIESCE"
systemctl disable --now zigbee2mqtt.service 2>/dev/null || true
systemctl reset-failed zigbee2mqtt.service 2>/dev/null || true
echo "zigbee2mqtt: stopped/disabled"

section "SAFETY CHECK"
[[ -f "${CONFIG_FILE}" ]] || fail "Missing ${CONFIG_FILE}"
[[ -f "${ZSTACK_TEMPLATE}" ]] || fail "Missing ${ZSTACK_TEMPLATE}"
[[ -e "${SERIAL_BY_ID}" ]] || fail "Coordinator not present at ${SERIAL_BY_ID}"

for state_path in "${DATA_DIR}/database.db" "${DATA_DIR}/coordinator_backup.json"; do
    if [[ -e "${state_path}" ]]; then
        fail "Persistent Zigbee state exists: ${state_path}; refusing automatic recovery"
    fi
done

python3 - "${CONFIG_FILE}" "${SERIAL_BY_ID}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
serial = sys.argv[2]
text = path.read_text(encoding="utf-8")

checks = [
    (r"(?m)^version:\s*5\s*$", "configuration version is not 5"),
    (r"(?m)^\s*server:\s*[\"']?mqtt://127\.0\.0\.1:1883[\"']?\s*$", "unexpected MQTT server"),
    (r"(?m)^\s*last_seen:\s*ISO_8601\s*$", "expected last_seen setting missing"),
]
for pattern, message in checks:
    if re.search(pattern, text) is None:
        raise SystemExit(f"ERROR: {message}")

lines = text.splitlines()
serial_start = None
serial_end = None
for index, line in enumerate(lines):
    if re.fullmatch(r"serial:\s*", line):
        serial_start = index
        break
if serial_start is None:
    raise SystemExit("ERROR: serial block missing")

for index in range(serial_start + 1, len(lines)):
    line = lines[index]
    if line and not line[0].isspace() and not line.startswith("#"):
        serial_end = index
        break
if serial_end is None:
    serial_end = len(lines)

block = lines[serial_start + 1:serial_end]
port_values = []
adapter_values = []
for line in block:
    m = re.fullmatch(r"\s+port:\s*[\"']?(.+?)[\"']?\s*", line)
    if m:
        port_values.append(m.group(1))
    m = re.fullmatch(r"\s+adapter:\s*(\S+)\s*", line)
    if m:
        adapter_values.append(m.group(1))

if port_values != [serial]:
    raise SystemExit(f"ERROR: unexpected serial port in probe config: {port_values!r}")
if adapter_values:
    raise SystemExit(f"ERROR: adapter already specified in current config: {adapter_values!r}")

# The failed native autodetection can replace GENERATE network values with
# concrete credentials before the radio opens. That mutation is expected and
# does not mean a Zigbee network exists; persistent-state checks above are the
# authority for deciding whether automatic recovery is safe.
print("configuration shape: expected failed-autodetect probe")
PY

section "PRESERVE FAILED CONFIG"
if [[ -e "${BACKUP_FILE}" ]]; then
    fail "Backup already exists: ${BACKUP_FILE}; refusing to overwrite"
fi
cp -a "${CONFIG_FILE}" "${BACKUP_FILE}"
echo "preserved: ${BACKUP_FILE}"

section "INSTALL EXPLICIT ZSTACK PROBE"
install -m 0600 -o wentylacja -g wentylacja "${ZSTACK_TEMPLATE}" "${CONFIG_FILE}"
echo "adapter: zstack"
echo "baudrate: 115200"
echo "rtscts: false"
echo "serial: ${SERIAL_BY_ID}"
echo "persistent Zigbee state: absent"

echo
echo "Recovery PASS: failed autodetect configuration preserved; explicit zstack probe staged."
