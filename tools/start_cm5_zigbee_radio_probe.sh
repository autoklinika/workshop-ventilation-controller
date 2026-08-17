#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
Z2M_VERSION="2.13.0"
DATA_DIR="/var/lib/zigbee2mqtt"
CONFIG_FILE="${DATA_DIR}/configuration.yaml"
AUTODETECT_TEMPLATE="${ROOT_DIR}/deploy/cm5/zigbee/zigbee2mqtt/configuration.autodetect.yaml"
ZSTACK_TEMPLATE="${ROOT_DIR}/deploy/cm5/zigbee/zigbee2mqtt/configuration.zstack-probe.yaml"
SERIAL_BY_ID="/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_822f54682ed0f01198f6423758f97c40-if00-port0"
STATE_TOPIC="zigbee2mqtt/bridge/state"
INFO_TOPIC="zigbee2mqtt/bridge/info"
PROBE_DROPIN_DIR="/run/systemd/system/zigbee2mqtt.service.d"
PROBE_DROPIN="${PROBE_DROPIN_DIR}/90-wvc-radio-probe.conf"
ZSTACK_FAILED_BACKUP="${DATA_DIR}/configuration.zstack-generated-failed.yaml"

state_file=""
info_file=""

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

cleanup_files() {
    [[ -z "${state_file}" ]] || rm -f "${state_file}" || true
    [[ -z "${info_file}" ]] || rm -f "${info_file}" || true
}

remove_probe_dropin() {
    if [[ -e "${PROBE_DROPIN}" ]]; then
        rm -f "${PROBE_DROPIN}" || true
        rmdir "${PROBE_DROPIN_DIR}" 2>/dev/null || true
        systemctl daemon-reload 2>/dev/null || true
    fi
}

on_exit() {
    local rc=$?
    trap - EXIT
    cleanup_files
    remove_probe_dropin
    if [[ ${rc} -ne 0 ]]; then
        echo
        echo "===== STAGE 3 FAILURE CLEANUP ====="
        systemctl stop zigbee2mqtt.service 2>/dev/null || true
        systemctl disable zigbee2mqtt.service 2>/dev/null || true
        echo "zigbee2mqtt stopped/disabled after unsuccessful probe"
    fi
    exit "${rc}"
}
trap on_exit EXIT

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/start_cm5_zigbee_radio_probe.sh"
fi

section "QUIESCE PREVIOUS PROBE"
# A failed probe must never be left in a restart loop. This also makes the
# script safe after the earlier Stage 3 cleanup bug.
systemctl disable --now zigbee2mqtt.service 2>/dev/null || true
systemctl reset-failed zigbee2mqtt.service 2>/dev/null || true
echo "zigbee2mqtt: stopped before probe"

section "PRECHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service; do
    if systemctl is-active --quiet "${unit}"; then
        echo "${unit}: active"
    else
        fail "${unit} is not active"
    fi
done

[[ -x /usr/bin/node ]] || fail "Node.js is not installed"
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[[ "${node_major}" == "24" ]] || fail "Expected Node.js 24.x, got $(node --version)"

[[ -f /opt/zigbee2mqtt/package.json ]] || fail "Zigbee2MQTT installation not found"
package_version="$(cd /opt/zigbee2mqtt && node -p 'require("./package.json").version')"
[[ "${package_version}" == "${Z2M_VERSION}" ]] || fail "Expected Zigbee2MQTT ${Z2M_VERSION}, got ${package_version}"
[[ -f /opt/zigbee2mqtt/dist/.hash ]] || fail "Zigbee2MQTT runtime build missing; rerun Stage 2 installer"
expected_hash="$(git -C /opt/zigbee2mqtt rev-parse --short=8 HEAD)"
runtime_hash="$(tr -d '\r\n' </opt/zigbee2mqtt/dist/.hash)"
[[ "${runtime_hash}" == "${expected_hash}" ]] || fail "Zigbee2MQTT runtime build hash mismatch (${runtime_hash} != ${expected_hash})"
echo "node: $(node --version)"
echo "zigbee2mqtt: ${package_version}"
echo "runtime build: ${runtime_hash}"

[[ -e "${SERIAL_BY_ID}" ]] || fail "Coordinator not present at ${SERIAL_BY_ID}"
real_port="$(readlink -f "${SERIAL_BY_ID}")"
echo "serial: ${SERIAL_BY_ID} -> ${real_port}"
ls -l "${real_port}"

if command -v fuser >/dev/null 2>&1 && fuser "${real_port}" >/dev/null 2>&1; then
    fuser -v "${real_port}" >&2 || true
    fail "Coordinator serial port is already in use"
fi

[[ -f "${AUTODETECT_TEMPLATE}" ]] || fail "Missing autodetect reference template"
[[ -f "${ZSTACK_TEMPLATE}" ]] || fail "Missing zstack probe template"
[[ -f "${CONFIG_FILE}" ]] || fail "Expected existing Stage 3 probe configuration at ${CONFIG_FILE}"

# No successful network initialization should have happened during the failed
# autodetection runs. Refuse to modify radio settings if persistent Zigbee
# state already exists.
for state_path in "${DATA_DIR}/database.db" "${DATA_DIR}/coordinator_backup.json"; do
    if [[ -e "${state_path}" ]]; then
        fail "Persistent Zigbee state already exists: ${state_path}; manual review required before another driver probe"
    fi
done

section "SELECT EXPLICIT ZSTACK PROBE"
if cmp -s "${CONFIG_FILE}" "${AUTODETECT_TEMPLATE}"; then
    cp -a "${CONFIG_FILE}" "${DATA_DIR}/configuration.autodetect-failed.yaml"
    install -m 0600 -o wentylacja -g wentylacja "${ZSTACK_TEMPLATE}" "${CONFIG_FILE}"
    echo "previous native autodetection configuration preserved"
    echo "configuration upgraded to explicit adapter: zstack"
elif cmp -s "${CONFIG_FILE}" "${ZSTACK_TEMPLATE}"; then
    echo "explicit zstack probe configuration already present: safe retry"
else
    # Zigbee2MQTT serializes configuration.yaml before the coordinator has
    # necessarily answered. After a failed zstack probe this can replace
    # GENERATE values and fold the long serial path, so byte-for-byte cmp is
    # no longer sufficient. With persistent Zigbee state absent (checked
    # above), accept only the exact WVC zstack transport settings and restore
    # the canonical probe template before retrying.
    if python3 - "${CONFIG_FILE}" "${SERIAL_BY_ID}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_port = sys.argv[2]
text = path.read_text(encoding="utf-8")

required = [
    (r"(?m)^version:\s*5\s*$", "configuration version is not 5"),
    (r"(?m)^\s*server:\s*[\"']?mqtt://127\.0\.0\.1:1883[\"']?\s*$", "unexpected MQTT server"),
    (r"(?m)^\s*adapter:\s*[\"']?zstack[\"']?\s*$", "adapter is not zstack"),
    (r"(?m)^\s*baudrate:\s*115200\s*$", "baudrate is not 115200"),
    (r"(?m)^\s*rtscts:\s*false\s*$", "rtscts is not false"),
]
for pattern, message in required:
    if re.search(pattern, text, flags=re.IGNORECASE) is None:
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
port_entries = []
for rel_index, line in enumerate(block):
    match = re.fullmatch(r"(\s+)port:\s*(.*?)\s*", line)
    if not match:
        continue
    indent = len(match.group(1))
    raw_value = match.group(2).strip()
    if raw_value in {">", ">-", ">+", "|", "|-", "|+"}:
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
    port_entries.append((value, encoding))

if len(port_entries) != 1:
    raise SystemExit(f"ERROR: expected exactly one serial.port, got {port_entries!r}")
port, encoding = port_entries[0]
if port != expected_port:
    raise SystemExit(f"ERROR: unexpected serial port: {port!r}")

print("configuration shape: expected generated zstack probe")
print(f"serial.port encoding: {encoding}")
print(f"serial.port: {port}")
PY
    then
        if [[ ! -e "${ZSTACK_FAILED_BACKUP}" ]]; then
            cp -a "${CONFIG_FILE}" "${ZSTACK_FAILED_BACKUP}"
            echo "preserved generated failed zstack config: ${ZSTACK_FAILED_BACKUP}"
        else
            echo "generated failed zstack backup already present: ${ZSTACK_FAILED_BACKUP}"
        fi
        install -m 0600 -o wentylacja -g wentylacja "${ZSTACK_TEMPLATE}" "${CONFIG_FILE}"
        echo "canonical explicit zstack probe restored: safe retry"
    else
        fail "Existing ${CONFIG_FILE} is not a recognized WVC probe configuration; refusing to overwrite"
    fi
fi

echo "adapter: zstack"
echo "baudrate: 115200"
echo "rtscts: false"
echo "frontend: disabled"
echo "permit_join: not opened"

section "START EXPLICIT ZSTACK PROBE"
# Prevent systemd from retrying a wrong protocol repeatedly. The runtime
# drop-in exists only for this probe and is always removed by the EXIT trap.
install -d -m 0755 "${PROBE_DROPIN_DIR}"
printf '[Service]\nRestart=no\n' >"${PROBE_DROPIN}"
systemctl daemon-reload
systemctl reset-failed zigbee2mqtt.service 2>/dev/null || true

state_file="$(mktemp)"
info_file="$(mktemp)"
mosquitto_sub -h 127.0.0.1 -p 1883 -t "${STATE_TOPIC}" -C 1 -W 45 >"${state_file}" &
state_sub_pid=$!
sleep 0.2
systemctl start --no-block zigbee2mqtt.service

# Do not wait the full MQTT timeout when the process already failed.
for _ in $(seq 1 45); do
    if [[ -s "${state_file}" ]]; then
        break
    fi
    if systemctl is-failed --quiet zigbee2mqtt.service; then
        break
    fi
    sleep 1
done

if [[ ! -s "${state_file}" ]]; then
    kill "${state_sub_pid}" 2>/dev/null || true
    wait "${state_sub_pid}" 2>/dev/null || true
    echo "No bridge online state received."
    echo
    echo "===== ZIGBEE2MQTT JOURNAL ====="
    journalctl -u zigbee2mqtt.service -n 180 --no-pager || true
    fail "Explicit zstack radio probe failed"
fi
wait "${state_sub_pid}" 2>/dev/null || true

bridge_state="$(tr -d '\r\n' <"${state_file}")"
echo "bridge/state: ${bridge_state}"
case "${bridge_state}" in
    online|*'"state":"online"'*) ;;
    *)
        journalctl -u zigbee2mqtt.service -n 180 --no-pager || true
        fail "Unexpected bridge state: ${bridge_state}"
        ;;
esac

section "BRIDGE INFO"
if ! mosquitto_sub -h 127.0.0.1 -p 1883 -t "${INFO_TOPIC}" -C 1 -W 10 >"${info_file}"; then
    journalctl -u zigbee2mqtt.service -n 180 --no-pager || true
    fail "Unable to read retained ${INFO_TOPIC}"
fi

python3 - "${info_file}" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
try:
    value = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"bridge/info is not valid JSON: {exc}: {raw!r}")

print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
coordinator = value.get("coordinator") or {}
print("\n--- coordinator summary ---")
print("type:", coordinator.get("type"))
print("ieee_address:", coordinator.get("ieee_address"))
print("meta:", json.dumps(coordinator.get("meta"), ensure_ascii=False, sort_keys=True))
print("network:", json.dumps(value.get("network"), ensure_ascii=False, sort_keys=True))
print("permit_join:", value.get("permit_join"))
if value.get("permit_join") is True:
    raise SystemExit("SECURITY CHECK FAILED: permit_join unexpectedly true")
PY

section "SERVICE ENABLE"
remove_probe_dropin
systemctl enable zigbee2mqtt.service
systemctl is-active --quiet zigbee2mqtt.service || fail "zigbee2mqtt.service is not active after successful probe"

section "REGRESSION CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done
ss -lntp | grep -E '127\.0\.0\.1:1883|0\.0\.0\.0:18091' || true

section "RESULT"
echo "Stage 3 PASS: coordinator initialized using explicit zstack driver."
echo "Pairing has NOT been opened. Do not pair devices yet."
