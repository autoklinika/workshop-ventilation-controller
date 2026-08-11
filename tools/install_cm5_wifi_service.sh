#!/usr/bin/env bash
set -euo pipefail

PROFILE="wvc-sensor-service"
IFACE="wlan0"
SSID="WVC-SERVICE"
ADDRESS="10.55.0.1/24"
CHANNEL="6"
ACTIVATE=0

usage() {
    cat <<'USAGE'
Usage: sudo bash tools/install_cm5_wifi_service.sh [--activate]

Installs the isolated CM5 service Wi-Fi configuration for KAmod/SEN55 nodes.
The WVC-SERVICE AP is intentionally open at layer 2. Application heartbeats
remain authenticated per node with HMAC-SHA256, and nftables blocks all local
services except the explicitly allowed service protocol.

Without --activate the script prepares the NetworkManager profile and system
files but leaves the currently active Wi-Fi connection untouched. With
--activate it switches wlan0 to WVC-SERVICE and starts firewall and DHCP units.
USAGE
}

while (($#)); do
    case "$1" in
        --activate) ACTIVATE=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root (sudo)." >&2
    exit 1
fi

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

for command in nmcli nft dnsmasq ip systemctl; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "Missing required command: $command" >&2
        exit 1
    }
done

if ! nmcli -t -f GENERAL.DEVICE device show "$IFACE" >/dev/null 2>&1; then
    echo "Network interface $IFACE is not managed by NetworkManager." >&2
    exit 1
fi

install -d -m 0755 /etc/dnsmasq.d /etc/nftables.d /var/lib/misc
install -m 0644 \
    "$REPO_ROOT/deploy/cm5/wifi/dnsmasq/wvc-sensor-service.conf" \
    /etc/dnsmasq.d/wvc-sensor-service.conf
install -m 0644 \
    "$REPO_ROOT/deploy/cm5/wifi/nftables/wvc-sensor-service.nft" \
    /etc/nftables.d/wvc-sensor-service.nft
install -m 0644 \
    "$REPO_ROOT/deploy/cm5/wifi/systemd/wvc-sensor-firewall.service" \
    /etc/systemd/system/wvc-sensor-firewall.service
install -m 0644 \
    "$REPO_ROOT/deploy/cm5/wifi/systemd/wvc-sensor-dhcp.service" \
    /etc/systemd/system/wvc-sensor-dhcp.service

nft --check --file /etc/nftables.d/wvc-sensor-service.nft
dnsmasq --test --conf-file=/etc/dnsmasq.d/wvc-sensor-service.conf

if ! nmcli -g connection.id connection show "$PROFILE" >/dev/null 2>&1; then
    nmcli connection add type wifi ifname "$IFACE" con-name "$PROFILE" ssid "$SSID"
fi

nmcli connection modify "$PROFILE" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel "$CHANNEL" \
    802-11-wireless.ap-isolation yes \
    802-11-wireless.powersave 2 \
    ipv4.method manual \
    ipv4.addresses "$ADDRESS" \
    ipv4.never-default yes \
    ipv4.gateway "" \
    ipv4.dns "" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 200

KEY_MGMT="$(nmcli -g 802-11-wireless-security.key-mgmt connection show "$PROFILE" 2>/dev/null || true)"
if [[ -n "$KEY_MGMT" && "$KEY_MGMT" != "--" ]]; then
    nmcli connection modify "$PROFILE" remove 802-11-wireless-security
fi
unset KEY_MGMT

systemctl daemon-reload
systemctl enable wvc-sensor-firewall.service wvc-sensor-dhcp.service

if [[ $ACTIVATE -eq 0 ]]; then
    cat <<EOF2
Configuration installed but not activated.
The current wlan0 connection was left untouched.
Run again with --activate while administrative access is available through eth0.
EOF2
    exit 0
fi

ACTIVE_WIFI="$(nmcli -t -f NAME,TYPE,DEVICE connection show --active | awk -F: -v iface="$IFACE" '$2=="wifi" && $3==iface {print $1; exit}')"
if [[ -n "$ACTIVE_WIFI" && "$ACTIVE_WIFI" != "$PROFILE" ]]; then
    nmcli connection modify "$ACTIVE_WIFI" connection.autoconnect no
    nmcli connection down "$ACTIVE_WIFI" || true
fi

nmcli --wait 30 connection up "$PROFILE" ifname "$IFACE"
systemctl restart wvc-sensor-firewall.service
systemctl restart wvc-sensor-dhcp.service

bash "$REPO_ROOT/tools/validate_cm5_wifi_service.sh"
