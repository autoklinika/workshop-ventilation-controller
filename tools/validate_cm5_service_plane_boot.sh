#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

# The OTA-capable service agent is the production successor of the narrow
# heartbeat receiver. Keep this check independent from ventilation-core.
systemctl is-enabled --quiet wvc-service-agent.service \
    || fail "wvc-service-agent.service is not enabled for boot"
pass "service agent enabled for boot"

systemctl is-active --quiet wvc-service-agent.service \
    || fail "wvc-service-agent.service is not active"
pass "service agent active"

if systemctl is-enabled --quiet wvc-service-heartbeat.service 2>/dev/null; then
    fail "legacy wvc-service-heartbeat.service is enabled"
fi
pass "legacy heartbeat receiver disabled"

if systemctl is-active --quiet wvc-service-heartbeat.service 2>/dev/null; then
    fail "legacy wvc-service-heartbeat.service is active"
fi
pass "legacy heartbeat receiver inactive"

printf '\nSERVICE PLANE BOOT VALIDATION: PASS\n'
