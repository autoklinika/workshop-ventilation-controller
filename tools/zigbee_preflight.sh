#!/usr/bin/env bash
set -euo pipefail

SERIAL_BY_ID="${ZIGBEE_SERIAL:-/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_822f54682ed0f01198f6423758f97c40-if00-port0}"

section() {
    printf '\n===== %s =====\n' "$1"
}

section "SYSTEM"
uname -a
if [[ -r /etc/os-release ]]; then
    cat /etc/os-release
fi

section "RESOURCES"
free -h || true
df -h / /opt /var 2>/dev/null || df -h /

section "USB"
lsusb || true

section "ZIGBEE SERIAL"
printf 'configured_by_id: %s\n' "${SERIAL_BY_ID}"
if [[ -e "${SERIAL_BY_ID}" ]]; then
    real_port="$(readlink -f "${SERIAL_BY_ID}")"
    printf 'resolved_port: %s\n' "${real_port}"
    ls -l "${SERIAL_BY_ID}" "${real_port}"
    stat -c 'owner=%U group=%G mode=%a device=%n' "${real_port}"
else
    echo "ERROR: Zigbee serial adapter not present at configured by-id path"
    exit 2
fi

section "UDEV"
udevadm info --query=property --name="${real_port}" | grep -E '^(DEVNAME|ID_VENDOR|ID_VENDOR_ID|ID_MODEL|ID_MODEL_ID|ID_SERIAL|ID_SERIAL_SHORT)=' || true

section "USER / GROUPS"
id
getent group dialout || true

section "PORT USERS"
if command -v fuser >/dev/null 2>&1; then
    fuser -v "${real_port}" 2>&1 || true
else
    echo "fuser: not installed"
fi

section "SOFTWARE"
printf 'git: '; git --version || true
printf 'node: '; node --version 2>/dev/null || echo 'not installed'
printf 'npm: '; npm --version 2>/dev/null || echo 'not installed'
printf 'pnpm: '; pnpm --version 2>/dev/null || echo 'not installed'
printf 'mosquitto: '; mosquitto -h 2>&1 | head -n 1 || echo 'not installed'
printf 'mosquitto_sub: '; command -v mosquitto_sub || echo 'not installed'

section "SERVICES"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s ' "${unit}"
    systemctl is-active "${unit}" 2>/dev/null || true
done

section "LISTENERS"
ss -lntup 2>/dev/null | grep -E ':(1883|8080|18090|18091)\b' || true

section "GITHUB"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'branch: '; git branch --show-current
    printf 'head:   '; git rev-parse HEAD
    git status --short
else
    echo "not inside a Git work tree"
fi

section "RESULT"
echo "Zigbee USB preflight completed. No system configuration was changed."
