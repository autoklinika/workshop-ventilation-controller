#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEYS_SOURCE="${1:-}"
KEYS_TARGET="/etc/wvc-service-heartbeat/keys.json"
UNIT_TARGET="/etc/systemd/system/wvc-service-agent.service"
NFT_TARGET="/etc/nftables.d/wvc-sensor-service.nft"
CTL_TARGET="/usr/local/bin/wvc-servicectl"
SOCKET_PATH="/run/wvc-service-agent/service-agent.sock"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root." >&2
    exit 1
fi
if [[ -z "${KEYS_SOURCE}" || ! -f "${KEYS_SOURCE}" ]]; then
    echo "Usage: sudo bash $0 /secure/path/keys.json" >&2
    exit 1
fi

python3 - "${KEYS_SOURCE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(value, dict) or not isinstance(value.get("nodes"), dict) or not value["nodes"]:
    raise SystemExit("Key registry must contain a non-empty nodes object")
for node_id, node in value["nodes"].items():
    if not isinstance(node_id, str) or not isinstance(node, dict):
        raise SystemExit("Invalid node registry entry")
    key = node.get("hmac_key_hex", "")
    if len(key) != 64 or any(c not in "0123456789abcdefABCDEF" for c in key):
        raise SystemExit(f"Invalid HMAC key for {node_id}")
PY

install -d -m 0700 -o wentylacja -g wentylacja /etc/wvc-service-heartbeat
source_real="$(realpath "${KEYS_SOURCE}")"
target_real="$(realpath -m "${KEYS_TARGET}")"
if [[ "${source_real}" != "${target_real}" ]]; then
    install -m 0600 -o wentylacja -g wentylacja "${KEYS_SOURCE}" "${KEYS_TARGET}"
else
    chown wentylacja:wentylacja "${KEYS_TARGET}"
    chmod 0600 "${KEYS_TARGET}"
fi
install -m 0644 "${ROOT_DIR}/deploy/systemd/wvc-service-agent.service" "${UNIT_TARGET}"
install -m 0644 "${ROOT_DIR}/deploy/cm5/wifi/nftables/wvc-sensor-service.nft" "${NFT_TARGET}"
install -m 0755 "${ROOT_DIR}/tools/wvc-servicectl" "${CTL_TARGET}"

/usr/sbin/nft --check --file "${NFT_TARGET}"
systemctl daemon-reload
systemctl reload wvc-sensor-firewall.service

# The service agent replaces the narrow heartbeat receiver and keeps its
# persistent replay state in /var/lib/wvc-service-heartbeat.
systemctl disable --now wvc-service-heartbeat.service 2>/dev/null || true
systemctl enable wvc-service-agent.service
# Keys are loaded only during process startup, therefore installation always
# performs a full restart after replacing or validating the registry.
systemctl restart wvc-service-agent.service

# systemctl may report the process as running before the Python daemon has
# created and started serving its Unix socket. Wait for a real API response.
agent_status=""
agent_ready=false
for _ in $(seq 1 50); do
    if [[ -S "${SOCKET_PATH}" ]]; then
        if agent_status="$(sudo -u wentylacja wvc-servicectl status 2>&1)"; then
            agent_ready=true
            break
        fi
    fi
    sleep 0.2
done

if [[ "${agent_ready}" != true ]]; then
    echo "Service agent API did not become ready." >&2
    [[ -n "${agent_status}" ]] && echo "${agent_status}" >&2
    journalctl -u wvc-service-agent.service -n 50 --no-pager >&2 || true
    exit 1
fi

systemctl --no-pager --full status wvc-service-agent.service
ss -lunp | grep -E '10\.55\.0\.1:45551|0\.0\.0\.0:45551' || true
printf '%s\n' "${agent_status}"
