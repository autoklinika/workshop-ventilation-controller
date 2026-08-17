#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="/var/lib/zigbee2mqtt"
CONFIG_FILE="${DATA_DIR}/configuration.yaml"
ZSTACK_TEMPLATE="${ROOT_DIR}/deploy/cm5/zigbee/zigbee2mqtt/configuration.zstack-probe.yaml"
SERIAL_BY_ID="/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_822f54682ed0f01198f6423758f97c40-if00-port0"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/restage_cm5_zigbee_zstack_probe.sh"
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
        fail "Persistent Zigbee state exists: ${state_path}; refusing automatic restage"
    fi
done

python3 - "${CONFIG_FILE}" "${SERIAL_BY_ID}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
serial = sys.argv[2]
text = path.read_text(encoding="utf-8")
lines = text.splitlines()

def require(pattern: str, message: str) -> None:
    if re.search(pattern, text) is None:
        raise SystemExit(f"ERROR: {message}")

require(r"(?m)^version:\s*5\s*$", "configuration version is not 5")
require(r"(?m)^\s*server:\s*[\"']?mqtt://127\.0\.0\.1:1883[\"']?\s*$", "unexpected MQTT server")
require(r"(?ms)^homeassistant:\s*\n\s+enabled:\s*false\s*$", "Home Assistant must remain disabled")
require(r"(?ms)^frontend:\s*\n\s+enabled:\s*false\s*$", "frontend must remain disabled")
require(r"(?m)^\s*last_seen:\s*ISO_8601\s*$", "expected last_seen setting missing")

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
values = {}

for rel_index, line in enumerate(block):
    m = re.fullmatch(r"(\s+)(port|adapter|baudrate|rtscts):\s*(.*?)\s*", line)
    if not m:
        continue
    indent = len(m.group(1))
    key = m.group(2)
    raw_value = m.group(3).strip()

    if key == "port" and raw_value in {">", ">-", ">+", "|", "|-", "|+"}:
        parts = []
        for following in block[rel_index + 1:]:
            if not following.strip():
                continue
            following_indent = len(following) - len(following.lstrip())
            if following_indent <= indent:
                break
            parts.append(following.strip())
        value = "".join(parts)
        encoding = f"block scalar {raw_value}"
    else:
        value = raw_value.strip("\"'")
        encoding = "inline scalar"

    if key in values:
        raise SystemExit(f"ERROR: duplicate serial.{key}")
    values[key] = (value, encoding)

required = {"port", "adapter", "baudrate", "rtscts"}
missing = sorted(required - values.keys())
if missing:
    raise SystemExit(f"ERROR: missing serial settings: {missing}")

port, port_encoding = values["port"]
adapter, _ = values["adapter"]
baudrate, _ = values["baudrate"]
rtscts, _ = values["rtscts"]

if port != serial:
    raise SystemExit(f"ERROR: unexpected serial.port: {port!r}")
if adapter != "zstack":
    raise SystemExit(f"ERROR: unexpected serial.adapter: {adapter!r}")
if baudrate != "115200":
    raise SystemExit(f"ERROR: unexpected serial.baudrate: {baudrate!r}")
if rtscts.lower() != "false":
    raise SystemExit(f"ERROR: unexpected serial.rtscts: {rtscts!r}")

print("configuration shape: expected explicit zstack probe")
print(f"serial.port encoding: {port_encoding}")
print(f"serial.port: {port}")
print("serial.adapter: zstack")
print("serial.baudrate: 115200")
print("serial.rtscts: false")
PY

section "PRESERVE SERIALIZED CONFIG"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="${DATA_DIR}/configuration.zstack-serialized-${stamp}.yaml"
cp -a "${CONFIG_FILE}" "${backup}"
echo "preserved: ${backup}"

section "RESTAGE REFERENCE ZSTACK PROBE"
install -m 0600 -o wentylacja -g wentylacja "${ZSTACK_TEMPLATE}" "${CONFIG_FILE}"
cmp -s "${CONFIG_FILE}" "${ZSTACK_TEMPLATE}" || fail "restaged configuration does not match reference template"
echo "adapter: zstack"
echo "baudrate: 115200"
echo "rtscts: false"
echo "serial: ${SERIAL_BY_ID}"
echo "persistent Zigbee state: absent"

echo
echo "Restage PASS: serialized zstack configuration preserved; reference probe configuration restored."
