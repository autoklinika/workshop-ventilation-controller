#!/usr/bin/env bash
set -uo pipefail

PROFILE="wvc-sensor-service"
IFACE="wlan0"
EXPECTED_SSID="WVC-SERVICE"
EXPECTED_ADDRESS="10.55.0.1/24"
FAILURES=0

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; FAILURES=$((FAILURES + 1)); }

expect_equal() {
    local description="$1" actual="$2" expected="$3"
    if [[ "$actual" == "$expected" ]]; then
        pass "$description = $expected"
    else
        fail "$description: expected '$expected', got '$actual'"
    fi
}

for command in nmcli iw ip nft systemctl sysctl ss; do
    command -v "$command" >/dev/null 2>&1 || {
        fail "required command missing: $command"
    }
done

if ((FAILURES)); then
    exit 1
fi

ACTIVE_PROFILE="$(nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null || true)"
MODE="$(nmcli -g 802-11-wireless.mode connection show "$PROFILE" 2>/dev/null || true)"
SSID="$(nmcli -g 802-11-wireless.ssid connection show "$PROFILE" 2>/dev/null || true)"
BAND="$(nmcli -g 802-11-wireless.band connection show "$PROFILE" 2>/dev/null || true)"
CHANNEL="$(nmcli -g 802-11-wireless.channel connection show "$PROFILE" 2>/dev/null || true)"
AP_ISOLATION="$(nmcli -g 802-11-wireless.ap-isolation connection show "$PROFILE" 2>/dev/null || true)"
POWERSAVE="$(nmcli -g 802-11-wireless.powersave connection show "$PROFILE" 2>/dev/null || true)"
KEY_MGMT="$(nmcli -g 802-11-wireless-security.key-mgmt connection show "$PROFILE" 2>/dev/null || true)"

expect_equal "active NetworkManager profile" "$ACTIVE_PROFILE" "$PROFILE"
expect_equal "Wi-Fi mode" "$MODE" "ap"
expect_equal "SSID" "$SSID" "$EXPECTED_SSID"
expect_equal "band" "$BAND" "bg"
expect_equal "channel" "$CHANNEL" "6"
case "$AP_ISOLATION" in
    1|yes) pass "AP isolation enabled" ;;
    *) fail "AP isolation: expected '1' or 'yes', got '$AP_ISOLATION'" ;;
esac
case "$POWERSAVE" in
    2|disable) pass "Wi-Fi power saving disabled" ;;
    *) fail "Wi-Fi power saving: expected '2' or 'disable', got '$POWERSAVE'" ;;
esac
if [[ -z "$KEY_MGMT" || "$KEY_MGMT" == "--" ]]; then
    pass "service AP has no layer-2 authentication"
else
    fail "service AP must be open, got key management '$KEY_MGMT'"
fi

if ip -4 -o addr show dev "$IFACE" | awk '{print $4}' | grep -Fxq "$EXPECTED_ADDRESS"; then
    pass "$IFACE has $EXPECTED_ADDRESS"
else
    fail "$IFACE does not have $EXPECTED_ADDRESS"
fi

if iw dev "$IFACE" info | grep -Eq '^[[:space:]]*type AP$'; then
    pass "$IFACE operates as AP"
else
    fail "$IFACE is not operating as AP"
fi

for unit in wvc-sensor-firewall.service wvc-sensor-dhcp.service; do
    if systemctl is-enabled --quiet "$unit"; then pass "$unit enabled"; else fail "$unit not enabled"; fi
    if systemctl is-active --quiet "$unit"; then pass "$unit active"; else fail "$unit not active"; fi
done

if nft list table inet wvc_sensor_service >/dev/null 2>&1; then
    pass "nftables table wvc_sensor_service loaded"
else
    fail "nftables table wvc_sensor_service missing"
fi

expect_equal "IPv4 forwarding" "$(sysctl -n net.ipv4.ip_forward)" "0"
expect_equal "IPv6 forwarding" "$(sysctl -n net.ipv6.conf.all.forwarding)" "0"

if ip route show default | grep -q " dev $IFACE "; then
    fail "default route exists through $IFACE"
else
    pass "no default route through $IFACE"
fi

if ss -lunp | grep -Eq '(^|[[:space:]])0\.0\.0\.0:67([[:space:]]|$)'; then
    pass "DHCP server listens on UDP/67"
else
    fail "DHCP server is not listening on UDP/67"
fi

printf '\nValidation result: %s\n' "$([[ $FAILURES -eq 0 ]] && echo PASS || echo FAIL)"
exit "$FAILURES"
