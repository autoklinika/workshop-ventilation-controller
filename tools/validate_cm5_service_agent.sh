#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOCKET="/run/wvc-service-agent/service-agent.sock"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

systemctl is-enabled --quiet wvc-service-agent.service || fail "service agent is not enabled for boot"
pass "service agent enabled for boot"

systemctl is-active --quiet wvc-service-agent.service || fail "service agent is not active"
pass "service agent active"

if systemctl is-enabled --quiet wvc-service-heartbeat.service 2>/dev/null; then
    fail "legacy heartbeat receiver is enabled; service-plane boot target is ambiguous"
fi
pass "legacy receiver disabled"

! systemctl is-active --quiet wvc-service-heartbeat.service || fail "legacy heartbeat receiver is still active"
pass "legacy receiver inactive"

[[ -r /etc/wvc-service-heartbeat/keys.json ]] || fail "key registry missing"
permissions="$(stat -c '%a' /etc/wvc-service-heartbeat/keys.json)"
[[ "${permissions}" == "600" ]] || fail "key registry permissions are ${permissions}, expected 600"
pass "key registry protected"

[[ -S "${SOCKET}" ]] || fail "service agent Unix socket missing"
socket_permissions="$(stat -c '%a' "${SOCKET}")"
[[ "${socket_permissions}" == "660" ]] || fail "socket permissions are ${socket_permissions}, expected 660"
pass "local service API socket protected"

ss -lun | grep -q '10.55.0.1:45551' || fail "UDP/45551 is not bound to 10.55.0.1"
pass "authenticated heartbeat UDP endpoint bound"

firewall_table="$(nft list table inet wvc_sensor_service)"
grep -q 'udp dport 45551 accept' <<<"${firewall_table}" || fail "heartbeat firewall rule missing"
grep -q 'ct state established,related accept' <<<"${firewall_table}" || fail "established OTA reply rule missing"
pass "minimal heartbeat and OTA reply rules present"

! grep -Eq 'tcp dport (22|80|443|45552)' <<<"${firewall_table}" || fail "unexpected CM5 TCP listener exposed"
pass "no service TCP ports exposed on CM5"

sysctl -n net.ipv4.ip_forward | grep -qx '0' || fail "IPv4 forwarding enabled"
sysctl -n net.ipv6.conf.all.forwarding | grep -qx '0' || fail "IPv6 forwarding enabled"
pass "routing remains disabled"

systemctl cat wvc-service-agent.service | grep -q 'ventilation_core.service_agent_ota' \
    || fail "OTA-capable service agent unit is not installed"
pass "OTA-capable service agent installed"

status_json="$(sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" \
    python3 -m ventilation_core.service_ctl status)"
python3 - "${status_json}" <<'PY'
import json
import sys

value = json.loads(sys.argv[1])
if value.get("ok") is not True:
    raise SystemExit("service API status failed")
agent = value.get("agent")
network = value.get("network")
nodes = value.get("nodes")
if not isinstance(agent, dict) or agent.get("ready") is not True:
    raise SystemExit("agent does not report ready")
if not isinstance(network, dict):
    raise SystemExit("network state missing")
if not isinstance(nodes, list) or not nodes:
    raise SystemExit("registered nodes missing")
PY
pass "local service API status valid"

sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" \
    python3 -m ventilation_core.service_ctl nodes >/dev/null
sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" \
    python3 -m ventilation_core.service_ctl network >/dev/null
sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" \
    python3 -m ventilation_core.service_ctl --help | grep -q 'ota-install'
sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" \
    python3 -m ventilation_core.service_ctl --help | grep -q 'ota-status'
pass "service API and manual OTA commands available"
