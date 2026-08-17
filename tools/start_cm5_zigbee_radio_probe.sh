#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
Z2M_VERSION="2.13.0"
Z2M_DIR="/opt/zigbee2mqtt"
DATA_DIR="/var/lib/zigbee2mqtt"
CONFIG_FILE="${DATA_DIR}/configuration.yaml"
CONFIG_TEMPLATE="${ROOT_DIR}/deploy/cm5/zigbee/zigbee2mqtt/configuration.probe.yaml"
SERIAL_BY_ID="/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_822f54682ed0f01198f6423758f97c40-if00-port0"
STATE_TOPIC="zigbee2mqtt/bridge/state"
INFO_TOPIC="zigbee2mqtt/bridge/info"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

cleanup_probe_failure() {
    local rc=$?
    if [[ ${rc} -ne 0 ]]; then
        echo
        echo "===== STAGE 3 FAILURE CLEANUP ====="
        systemctl stop zigbee2mqtt.service 2>/dev/null || true
        systemctl disable zigbee2mqtt.service 2>/dev/null || true
        echo "zigbee2mqtt stopped/disabled after unsuccessful probe"
    fi
    exit "${rc}"
}
trap cleanup_probe_failure EXIT

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/start_cm5_zigbee_radio_probe.sh"
fi

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

[[ -f "${Z2M_DIR}/package.json" ]] || fail "Zigbee2MQTT installation not found"
package_version="$(cd "${Z2M_DIR}" && node -p 'require("./package.json").version')"
[[ "${package_version}" == "${Z2M_VERSION}" ]] || fail "Expected Zigbee2MQTT ${Z2M_VERSION}, got ${package_version}"
echo "node: $(node --version)"
echo "zigbee2mqtt: ${package_version}"

# The hardened systemd unit intentionally blocks access to /home. Zigbee2MQTT
# must therefore already have a current dist/.hash and must not try to invoke
# pnpm/Corepack during service startup.
expected_hash="$(sudo -u wentylacja git -C "${Z2M_DIR}" rev-parse --short=8 HEAD)"
if [[ ! -f "${Z2M_DIR}/dist/.hash" ]]; then
    fail "Zigbee2MQTT runtime build missing (dist/.hash); rerun sudo bash tools/install_cm5_zigbee_stack.sh"
fi
built_hash="$(tr -d '\r\n' <"${Z2M_DIR}/dist/.hash")"
[[ "${built_hash}" == "${expected_hash}" ]] || fail "Zigbee2MQTT runtime build stale (${built_hash} != ${expected_hash}); rerun Stage 2 installer"
echo "runtime build: ${built_hash}"

[[ -e "${SERIAL_BY_ID}" ]] || fail "Coordinator not present at ${SERIAL_BY_ID}"
real_port="$(readlink -f "${SERIAL_BY_ID}")"
echo "serial: ${SERIAL_BY_ID} -> ${real_port}"
ls -l "${real_port}"

if command -v fuser >/dev/null 2>&1 && fuser "${real_port}" >/dev/null 2>&1; then
    fuser -v "${real_port}" >&2 || true
    fail "Coordinator serial port is already in use"
fi

[[ -f "${CONFIG_TEMPLATE}" ]] || fail "Missing staged configuration template: ${CONFIG_TEMPLATE}"

# Never retry once Zigbee2MQTT has created persistent network state. If only
# the untouched probe template exists (e.g. a failure before controller/radio
# startup), it is safe to resume the same probe without regenerating anything.
for state_file in "${DATA_DIR}/database.db" "${DATA_DIR}/coordinator_backup.json"; do
    if [[ -e "${state_file}" ]]; then
        fail "Existing Zigbee state detected: ${state_file}; refusing probe retry"
    fi
done

reuse_probe_config=false
if [[ -e "${CONFIG_FILE}" ]]; then
    if cmp -s "${CONFIG_FILE}" "${CONFIG_TEMPLATE}"; then
        reuse_probe_config=true
        echo "existing untouched probe configuration detected: safe retry"
    else
        fail "${CONFIG_FILE} already exists and differs from probe template; refusing to overwrite possible Zigbee network configuration"
    fi
fi

section "INSTALL CONTROLLED CONFIG"
install -d -m 0750 -o wentylacja -g wentylacja "${DATA_DIR}"
if [[ "${reuse_probe_config}" == false ]]; then
    install -m 0600 -o wentylacja -g wentylacja "${CONFIG_TEMPLATE}" "${CONFIG_FILE}"
    echo "configuration installed: ${CONFIG_FILE}"
else
    chown wentylacja:wentylacja "${CONFIG_FILE}"
    chmod 0600 "${CONFIG_FILE}"
    echo "configuration reused unchanged: ${CONFIG_FILE}"
fi
echo "adapter driver: omitted intentionally (native discovery probe)"
echo "frontend: disabled"
echo "availability: enabled"
echo "last_seen: ISO_8601"

section "START RADIO PROBE"
systemctl daemon-reload
systemctl reset-failed zigbee2mqtt.service 2>/dev/null || true
systemctl stop zigbee2mqtt.service 2>/dev/null || true

state_file="$(mktemp)"
info_file="$(mktemp)"
cleanup_files() {
    rm -f "${state_file:-}" "${info_file:-}"
}
trap 'cleanup_files; cleanup_probe_failure' EXIT

mosquitto_sub -h 127.0.0.1 -p 1883 -t "${STATE_TOPIC}" -C 1 -W 75 >"${state_file}" &
state_sub_pid=$!
sleep 0.2
systemctl start --no-block zigbee2mqtt.service

if ! wait "${state_sub_pid}"; then
    echo "No bridge state received within 75 seconds."
    echo
    echo "===== ZIGBEE2MQTT JOURNAL ====="
    journalctl -u zigbee2mqtt.service -n 160 --no-pager || true
    fail "Zigbee2MQTT radio probe did not reach MQTT online state"
fi

bridge_state="$(tr -d '\r\n' <"${state_file}")"
echo "bridge/state: ${bridge_state}"
case "${bridge_state}" in
    online|*'"state":"online"'*) ;;
    *)
        journalctl -u zigbee2mqtt.service -n 160 --no-pager || true
        fail "Unexpected bridge state: ${bridge_state}"
        ;;
esac

section "BRIDGE INFO"
if ! mosquitto_sub -h 127.0.0.1 -p 1883 -t "${INFO_TOPIC}" -C 1 -W 10 >"${info_file}"; then
    journalctl -u zigbee2mqtt.service -n 160 --no-pager || true
    fail "Unable to read retained ${INFO_TOPIC}"
fi

python3 - "${info_file}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8").strip()
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
systemctl enable zigbee2mqtt.service
systemctl is-active --quiet zigbee2mqtt.service || fail "zigbee2mqtt.service is not active after successful probe"

section "REGRESSION CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done
ss -lntp | grep -E '127\.0\.0\.1:1883|0\.0\.0\.0:18091' || true

section "RESULT"
echo "Stage 3 PASS: coordinator initialized and Zigbee2MQTT online."
echo "Pairing has NOT been opened. Do not pair devices yet."

cleanup_files
trap - EXIT
