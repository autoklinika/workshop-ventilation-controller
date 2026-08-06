#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOOKBACK_MINUTES="${1:-20}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo bash $0 [lookback_minutes]" >&2
    exit 1
fi
if [[ ! "${LOOKBACK_MINUTES}" =~ ^[0-9]+$ ]] || (( LOOKBACK_MINUTES < 1 )); then
    echo "lookback_minutes must be a positive integer" >&2
    exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
out_dir="/tmp/wvc-service-agent-dropout-${stamp}"
mkdir -p "${out_dir}"
since="${LOOKBACK_MINUTES} minutes ago"

run_as_wentylacja() {
    sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" "$@"
}

{
    echo "captured_at=$(date --iso-8601=seconds)"
    echo "lookback_minutes=${LOOKBACK_MINUTES}"
    echo "service_agent_state=$(systemctl is-active wvc-service-agent.service || true)"
    echo "service_agent_pid=$(systemctl show -p MainPID --value wvc-service-agent.service)"
    echo "ventilation_core_state=$(systemctl is-active ventilation-core.service || true)"
    echo "ventilation_core_pid=$(systemctl show -p MainPID --value ventilation-core.service)"
} > "${out_dir}/summary.txt"

run_as_wentylacja python3 -m ventilation_core.service_ctl status \
    > "${out_dir}/service-status.json" 2> "${out_dir}/service-status.err" || true
run_as_wentylacja python3 -m ventilation_core.ctl sensors \
    > "${out_dir}/sensor-bus.json" 2> "${out_dir}/sensor-bus.err" || true

journalctl -u wvc-service-agent.service --since "${since}" --no-pager -o short-iso \
    > "${out_dir}/service-agent-journal.txt" 2>&1 || true
journalctl -u ventilation-core.service --since "${since}" --no-pager -o short-iso \
    > "${out_dir}/ventilation-core-journal.txt" 2>&1 || true
journalctl -u NetworkManager.service --since "${since}" --no-pager -o short-iso \
    > "${out_dir}/networkmanager-journal.txt" 2>&1 || true
journalctl -u wpa_supplicant.service --since "${since}" --no-pager -o short-iso \
    > "${out_dir}/wpa-supplicant-journal.txt" 2>&1 || true
journalctl -k --since "${since}" --no-pager -o short-iso \
    > "${out_dir}/kernel-journal.txt" 2>&1 || true

nmcli -f GENERAL,IP4 device show wlan0 \
    > "${out_dir}/nmcli-wlan0.txt" 2>&1 || true
iw dev wlan0 station dump \
    > "${out_dir}/iw-station-dump.txt" 2>&1 || true
ip -4 neighbor show dev wlan0 \
    > "${out_dir}/ip-neighbor.txt" 2>&1 || true
cat /var/lib/misc/dnsmasq-wvc.leases \
    > "${out_dir}/dnsmasq-leases.txt" 2>&1 || true
ss -lunp > "${out_dir}/udp-listeners.txt" 2>&1 || true
nft -a list table inet wvc_sensor_service \
    > "${out_dir}/nftables.txt" 2>&1 || true

python3 - "${out_dir}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
status_path = out_dir / "service-status.json"
if not status_path.exists() or not status_path.read_text(encoding="utf-8").strip():
    print("Service status unavailable")
    raise SystemExit(0)

status = json.loads(status_path.read_text(encoding="utf-8"))
print("\nCURRENT SERVICE NODES")
for node in status.get("nodes", []):
    heartbeat = node.get("heartbeat") or {}
    transport = node.get("transport") or {}
    print(
        f"{node.get('node_id')}: "
        f"online={node.get('online')} "
        f"ip={node.get('source_ip')} "
        f"boot_id={heartbeat.get('boot_id')} "
        f"seq={heartbeat.get('seq')} "
        f"uptime_s={heartbeat.get('uptime_s')} "
        f"rssi={heartbeat.get('wifi_rssi_dbm')} "
        f"modbus_requests_total={heartbeat.get('modbus_requests_total')}"
    )
    if transport:
        print(
            "  transport: "
            f"accepted={transport.get('accepted_heartbeats')} "
            f"gap_events={transport.get('sequence_gap_events')} "
            f"missing_total={transport.get('missing_heartbeats_total')} "
            f"max_seq_gap={transport.get('max_sequence_gap')} "
            f"last_rx_gap_ms={transport.get('last_receive_gap_ms')} "
            f"max_rx_gap_ms={transport.get('max_receive_gap_ms')} "
            f"offline_transitions={transport.get('offline_transitions')} "
            f"boot_changes={transport.get('boot_changes')}"
        )
PY

echo
echo "RECENT HEARTBEAT TRANSITIONS AND GAPS"
grep -E 'heartbeat (online|offline)|heartbeat sequence gap|heartbeat boot changed|rejected heartbeat|service agent' \
    "${out_dir}/service-agent-journal.txt" || true

echo
echo "RECENT WLAN/KERNEL EVENTS"
cat \
    "${out_dir}/networkmanager-journal.txt" \
    "${out_dir}/wpa-supplicant-journal.txt" \
    "${out_dir}/kernel-journal.txt" |
grep -Ei 'wlan0|brcmfmac|deauth|disassoc|disconnect|firmware|timeout|88:13:bf|10\.55\.0\.' || true

echo
echo "Diagnostics saved in: ${out_dir}"
