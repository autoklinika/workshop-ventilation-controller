#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

systemctl is-enabled --quiet wvc-service-heartbeat.service || fail "receiver service is not enabled for boot"
pass "receiver service enabled for boot"

systemctl is-active --quiet wvc-service-heartbeat.service || fail "receiver service is not active"
pass "receiver service active"

if systemctl is-enabled --quiet wvc-service-agent.service 2>/dev/null; then
    fail "service agent is also enabled; service-plane boot target is ambiguous"
fi
pass "service agent disabled in legacy heartbeat mode"

if systemctl is-active --quiet wvc-service-agent.service 2>/dev/null; then
    fail "service agent is also active; UDP/45551 ownership is ambiguous"
fi
pass "service agent inactive in legacy heartbeat mode"

[[ -r /etc/wvc-service-heartbeat/keys.json ]] || fail "key registry missing"
permissions="$(stat -c '%a' /etc/wvc-service-heartbeat/keys.json)"
[[ "${permissions}" == "600" ]] || fail "key registry permissions are ${permissions}, expected 600"
pass "key registry protected"

ss -lun | grep -q '10.55.0.1:45551' || fail "UDP/45551 is not bound to 10.55.0.1"
pass "UDP/45551 receiver bound"

nft list table inet wvc_sensor_service | grep -q 'udp dport 45551 accept' || fail "firewall rule missing"
pass "minimal nftables rule present"

! nft list table inet wvc_sensor_service | grep -Eq 'tcp dport (22|80|443)' || fail "unexpected application TCP port exposed"
pass "no service TCP ports exposed"

sysctl -n net.ipv4.ip_forward | grep -qx '0' || fail "IPv4 forwarding enabled"
sysctl -n net.ipv6.conf.all.forwarding | grep -qx '0' || fail "IPv6 forwarding enabled"
pass "routing remains disabled"
