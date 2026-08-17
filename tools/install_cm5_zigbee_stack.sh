#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
Z2M_VERSION="2.13.0"
PNPM_VERSION="10.18.3"
NODE_MAJOR="24"
Z2M_DIR="/opt/zigbee2mqtt"
Z2M_DATA="/var/lib/zigbee2mqtt"
MOSQUITTO_CONF="/etc/mosquitto/conf.d/wvc-zigbee-local.conf"
UNIT_TARGET="/etc/systemd/system/zigbee2mqtt.service"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/install_cm5_zigbee_stack.sh"
fi

if [[ ! -d /home/wentylacja ]]; then
    fail "Expected service user 'wentylacja' is not present"
fi

section "PRECHECK"
if systemctl is-active --quiet ventilation-core.service; then
    echo "ventilation-core: active"
else
    fail "ventilation-core.service is not active; refusing infrastructure install"
fi
if systemctl is-active --quiet wvc-web-ui.service; then
    echo "wvc-web-ui: active"
else
    fail "wvc-web-ui.service is not active; refusing infrastructure install"
fi

section "APT PREREQUISITES"
apt-get update
apt-get install -y ca-certificates curl gnupg git make g++ gcc libsystemd-dev mosquitto mosquitto-clients

section "NODE.JS ${NODE_MAJOR}"
need_node_install=true
if command -v node >/dev/null 2>&1; then
    installed_major="$(node -p 'process.versions.node.split(".")[0]')"
    if [[ "${installed_major}" == "${NODE_MAJOR}" ]]; then
        need_node_install=false
        echo "Node.js already at required major: $(node --version)"
    else
        echo "Existing Node.js $(node --version) will be replaced with Node.js ${NODE_MAJOR}.x"
    fi
fi

if [[ "${need_node_install}" == true ]]; then
    tmp_setup="$(mktemp)"
    trap 'rm -f "${tmp_setup:-}"' EXIT
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o "${tmp_setup}"
    bash "${tmp_setup}"
    apt-get install -y nodejs
    rm -f "${tmp_setup}"
    trap - EXIT
fi

installed_major="$(node -p 'process.versions.node.split(".")[0]')"
[[ "${installed_major}" == "${NODE_MAJOR}" ]] || fail "Expected Node.js ${NODE_MAJOR}.x, got $(node --version)"
echo "node: $(node --version)"
echo "npm:  $(npm --version)"

section "PNPM"
if command -v corepack >/dev/null 2>&1; then
    corepack enable
else
    npm install -g "pnpm@${PNPM_VERSION}"
fi

section "MOSQUITTO LOCAL BROKER"
if ! grep -Eq '^[[:space:]]*include_dir[[:space:]]+/etc/mosquitto/conf\.d([[:space:]]|$)' /etc/mosquitto/mosquitto.conf; then
    fail "/etc/mosquitto/mosquitto.conf does not include /etc/mosquitto/conf.d"
fi
install -m 0644 "${ROOT_DIR}/deploy/cm5/zigbee/mosquitto/wvc-zigbee-local.conf" "${MOSQUITTO_CONF}"
systemctl enable mosquitto.service
systemctl restart mosquitto.service
systemctl is-active --quiet mosquitto.service || {
    journalctl -u mosquitto.service -n 80 --no-pager >&2 || true
    fail "mosquitto.service failed to start"
}

# Confirm broker is loopback-only and can actually exchange a message.
if ss -lnt | grep -Eq '0\.0\.0\.0:1883|\[::\]:1883'; then
    fail "MQTT broker unexpectedly listens on a non-loopback wildcard address"
fi
ss -lnt | grep -E '127\.0\.0\.1:1883' || fail "MQTT broker is not listening on 127.0.0.1:1883"

test_topic="wvc/zigbee/install-test"
test_payload="wvc-zigbee-$(date +%s)-$$"
test_file="$(mktemp)"
trap 'rm -f "${test_file:-}"' EXIT
mosquitto_sub -h 127.0.0.1 -p 1883 -t "${test_topic}" -C 1 -W 5 >"${test_file}" &
sub_pid=$!
sleep 0.4
mosquitto_pub -h 127.0.0.1 -p 1883 -t "${test_topic}" -m "${test_payload}"
wait "${sub_pid}" || fail "MQTT loopback publish/subscribe test timed out"
[[ "$(cat "${test_file}")" == "${test_payload}" ]] || fail "MQTT loopback test payload mismatch"
rm -f "${test_file}"
trap - EXIT
echo "MQTT loopback test: PASS"

section "ZIGBEE2MQTT ${Z2M_VERSION}"
if [[ -e "${Z2M_DIR}" && ! -d "${Z2M_DIR}/.git" ]]; then
    if [[ -n "$(find "${Z2M_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
        fail "${Z2M_DIR} exists and is not an expected Git checkout"
    fi
fi

if [[ ! -d "${Z2M_DIR}/.git" ]]; then
    # /opt is root-owned on Debian. Create the empty checkout directory as
    # root and hand only that directory to the unprivileged service user.
    # This keeps Git/npm work out of the root account while allowing a clean
    # first install and a safe retry after an interrupted Stage 2 run.
    rm -rf "${Z2M_DIR}"
    install -d -m 0755 -o wentylacja -g wentylacja "${Z2M_DIR}"
    sudo -u wentylacja env HOME=/home/wentylacja \
        git clone --branch "${Z2M_VERSION}" --depth 1 \
        https://github.com/Koenkk/zigbee2mqtt.git "${Z2M_DIR}"
else
    current_tag="$(sudo -u wentylacja git -C "${Z2M_DIR}" describe --tags --exact-match 2>/dev/null || true)"
    [[ "${current_tag}" == "${Z2M_VERSION}" ]] || fail "${Z2M_DIR} is at '${current_tag:-untagged}', expected ${Z2M_VERSION}"
fi

chown -R wentylacja:wentylacja "${Z2M_DIR}"
cd "${Z2M_DIR}"

# Corepack reads the packageManager field from Zigbee2MQTT's package.json.
# Pinning here also makes the intended tool version explicit in the installer.
sudo -u wentylacja env HOME=/home/wentylacja corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null 2>&1 || true
pnpm_actual="$(sudo -u wentylacja env HOME=/home/wentylacja pnpm --version)"
[[ "${pnpm_actual}" == "${PNPM_VERSION}" ]] || fail "Expected pnpm ${PNPM_VERSION}, got ${pnpm_actual}"
echo "pnpm: ${pnpm_actual}"
sudo -u wentylacja env HOME=/home/wentylacja pnpm install --frozen-lockfile

package_version="$(node -p 'require("./package.json").version')"
[[ "${package_version}" == "${Z2M_VERSION}" ]] || fail "Zigbee2MQTT package version mismatch: ${package_version}"
echo "zigbee2mqtt package: ${package_version}"

section "SYSTEMD STAGING"
install -d -m 0750 -o wentylacja -g wentylacja "${Z2M_DATA}"
install -m 0644 "${ROOT_DIR}/deploy/systemd/zigbee2mqtt.service" "${UNIT_TARGET}"
systemctl daemon-reload

# Stage 2 deliberately does not create configuration.yaml and does not start
# Zigbee2MQTT. The unit has ConditionPathExists on configuration.yaml so an
# accidental start cannot create a Zigbee network before we choose final radio
# settings and validate the adapter.
systemctl disable --now zigbee2mqtt.service 2>/dev/null || true

section "POSTCHECK"
echo "node:       $(node --version)"
echo "pnpm:       $(sudo -u wentylacja env HOME=/home/wentylacja pnpm --version)"
echo "mosquitto:  $(systemctl is-active mosquitto.service)"
echo "zigbee2mqtt installed version: ${package_version}"
echo "zigbee2mqtt service: $(systemctl is-active zigbee2mqtt.service 2>/dev/null || true)"
echo "configuration present: $([[ -f ${Z2M_DATA}/configuration.yaml ]] && echo yes || echo no)"
ss -lntp | grep -E '127\.0\.0\.1:1883' || true

echo
echo "Stage 2 PASS: MQTT and Zigbee2MQTT software installed; Zigbee network NOT started."
