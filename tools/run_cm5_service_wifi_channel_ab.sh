#!/usr/bin/env bash
set -euo pipefail

PROFILE="wvc-sensor-service"
IFACE="wlan0"
BASE_CHANNEL="6"
TEST_CHANNEL="11"
DURATION_SECONDS=300
SETTLE_SECONDS=20
LOG="/tmp/wvc-service-wifi-channel-ab-$(date +%Y%m%d-%H%M%S).log"
WORKDIR="$(mktemp -d /tmp/wvc-wifi-ab-XXXXXX)"
RESTORE_REQUIRED=0

usage() {
    cat <<'EOF'
Usage:
  sudo bash tools/run_cm5_service_wifi_channel_ab.sh [--duration SECONDS]

Runs a controlled service-plane Wi-Fi A/B test:
  A: WVC-SERVICE on channel 6
  B: WVC-SERVICE on channel 11

For each phase it records heartbeat transport counters for both KAmod nodes.
After the test (or on interruption) it restores channel 6 automatically.
The production SENSOR BUS / Modbus path is not modified.
EOF
}

while (($#)); do
    case "$1" in
        --duration)
            shift
            [[ $# -gt 0 ]] || { echo "FAIL: --duration requires seconds" >&2; exit 2; }
            DURATION_SECONDS="$1"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "FAIL: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

[[ "$DURATION_SECONDS" =~ ^[0-9]+$ ]] && ((DURATION_SECONDS >= 60)) || {
    echo "FAIL: duration must be an integer >= 60 seconds" >&2
    exit 2
}

if [[ ${EUID} -ne 0 ]]; then
    echo "FAIL: run as root with sudo" >&2
    exit 1
fi

for command in nmcli iw systemctl runuser python3 mktemp tee date sleep; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "FAIL: missing required command: $command" >&2
        exit 1
    }
done

command -v wvc-servicectl >/dev/null 2>&1 || {
    echo "FAIL: wvc-servicectl not found" >&2
    exit 1
}

exec > >(tee -a "$LOG") 2>&1

status_json() {
    runuser -u wentylacja -- wvc-servicectl status
}

configured_channel() {
    nmcli -g 802-11-wireless.channel connection show "$PROFILE" 2>/dev/null | tr -d '[:space:]'
}

actual_channel() {
    iw dev "$IFACE" info | awk '/^[[:space:]]*channel[[:space:]]+/ {print $2; exit}'
}

wait_nodes_online() {
    local deadline=$((SECONDS + 90))
    while ((SECONDS < deadline)); do
        if status_json | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
nodes={n.get("node_id"): n for n in d.get("nodes", [])}
ok=(d.get("ok") is True
    and (d.get("agent") or {}).get("ready") is True
    and (d.get("network") or {}).get("ready") is True
    and nodes.get("sensor-node-1", {}).get("online") is True
    and nodes.get("sensor-node-2", {}).get("online") is True)
raise SystemExit(0 if ok else 1)
' >/dev/null 2>&1; then
            echo "PASS: both KAmod nodes online"
            return 0
        fi
        sleep 2
    done
    echo "FAIL: both KAmod nodes did not become online within 90 s" >&2
    return 1
}

switch_channel() {
    local channel="$1"
    local configured actual
    configured="$(configured_channel)"
    actual="$(actual_channel)"

    echo
    echo "===== WVC-SERVICE CHANNEL $channel ====="

    if [[ "$configured" == "$channel" && "$actual" == "$channel" ]]; then
        echo "channel already active; no reconnect required"
        wait_nodes_online
        echo "settling for ${SETTLE_SECONDS}s"
        sleep "$SETTLE_SECONDS"
        return 0
    fi

    nmcli connection modify "$PROFILE" 802-11-wireless.channel "$channel"
    nmcli connection down "$PROFILE" >/dev/null 2>&1 || true
    nmcli --wait 30 connection up "$PROFILE" ifname "$IFACE" >/dev/null
    systemctl restart wvc-sensor-firewall.service
    systemctl restart wvc-sensor-dhcp.service
    sleep 3

    configured="$(configured_channel)"
    actual="$(actual_channel)"
    echo "configured channel: $configured"
    echo "actual channel:     $actual"
    [[ "$configured" == "$channel" && "$actual" == "$channel" ]] || {
        echo "FAIL: channel switch did not take effect" >&2
        return 1
    }

    wait_nodes_online
    echo "settling for ${SETTLE_SECONDS}s"
    sleep "$SETTLE_SECONDS"
}

restore_channel6() {
    local current
    current="$(configured_channel || true)"
    if [[ "$current" == "$BASE_CHANNEL" && "$(actual_channel 2>/dev/null || true)" == "$BASE_CHANNEL" ]]; then
        RESTORE_REQUIRED=0
        return 0
    fi

    echo
    echo "===== RESTORE WVC-SERVICE -> CHANNEL $BASE_CHANNEL ====="
    nmcli connection modify "$PROFILE" 802-11-wireless.channel "$BASE_CHANNEL" || true
    nmcli connection down "$PROFILE" >/dev/null 2>&1 || true
    nmcli --wait 30 connection up "$PROFILE" ifname "$IFACE" >/dev/null 2>&1 || true
    systemctl restart wvc-sensor-firewall.service >/dev/null 2>&1 || true
    systemctl restart wvc-sensor-dhcp.service >/dev/null 2>&1 || true
    sleep 3
    echo "configured channel: $(configured_channel || true)"
    echo "actual channel:     $(actual_channel 2>/dev/null || true)"
    RESTORE_REQUIRED=0
}

cleanup() {
    if ((RESTORE_REQUIRED)); then
        restore_channel6
    fi
    rm -rf "$WORKDIR"
}
trap cleanup EXIT INT TERM

summarize_delta() {
    local start_file="$1"
    local end_file="$2"
    local label="$3"
    python3 - "$start_file" "$end_file" "$label" <<'PY'
import json
import sys

start_path, end_path, label = sys.argv[1:4]
with open(start_path, encoding="utf-8") as f:
    start = json.load(f)
with open(end_path, encoding="utf-8") as f:
    end = json.load(f)

s_nodes = {n.get("node_id"): n for n in start.get("nodes", [])}
e_nodes = {n.get("node_id"): n for n in end.get("nodes", [])}

print(f"===== RESULT {label} =====")
for node_id in ("sensor-node-1", "sensor-node-2"):
    s = s_nodes[node_id]
    e = e_nodes[node_id]
    st = s.get("transport") or {}
    et = e.get("transport") or {}
    print(node_id)
    print("  online_end:              ", e.get("online"))
    print("  rssi_start/end:          ", s.get("wifi_rssi_dbm"), e.get("wifi_rssi_dbm"))
    print("  accepted_heartbeats:     ", et.get("accepted_heartbeats", 0) - st.get("accepted_heartbeats", 0))
    print("  sequence_gap_events:     ", et.get("sequence_gap_events", 0) - st.get("sequence_gap_events", 0))
    print("  missing_heartbeats_total:", et.get("missing_heartbeats_total", 0) - st.get("missing_heartbeats_total", 0))
    print("  offline_transitions:     ", et.get("offline_transitions", 0) - st.get("offline_transitions", 0))

    if node_id == "sensor-node-2":
        sh = s.get("heartbeat") or {}
        eh = e.get("heartbeat") or {}
        for key in (
            "heartbeat_send_attempts",
            "heartbeat_send_successes",
            "heartbeat_send_failures",
            "wifi_disconnect_events",
            "wifi_got_ip_events",
        ):
            if isinstance(sh.get(key), int) and isinstance(eh.get(key), int):
                print(f"  {key}_delta:", eh[key] - sh[key])
        print("  heartbeat_last_send_error:", eh.get("heartbeat_last_send_error"))
        print("  wifi_last_disconnect_reason:", eh.get("wifi_last_disconnect_reason"))
print()
PY
}

run_phase() {
    local label="$1"
    local channel="$2"
    local start_file="$WORKDIR/${label}-start.json"
    local end_file="$WORKDIR/${label}-end.json"

    switch_channel "$channel"

    echo
    echo "===== PHASE $label / CHANNEL $channel ====="
    echo "start: $(date --iso-8601=seconds)"
    status_json >"$start_file"

    local remaining="$DURATION_SECONDS"
    while ((remaining > 0)); do
        local step=30
        ((remaining < step)) && step="$remaining"
        sleep "$step"
        remaining=$((remaining - step))
        printf 'phase=%s channel=%s remaining=%ss\n' "$label" "$channel" "$remaining"
    done

    sleep 40
    status_json >"$end_file"
    echo "end:   $(date --iso-8601=seconds)"
    summarize_delta "$start_file" "$end_file" "$label"
}

echo "===== WVC SERVICE WI-FI CHANNEL A/B ====="
echo "start:          $(date --iso-8601=seconds)"
echo "log:            $LOG"
echo "phase duration: ${DURATION_SECONDS}s + 40s closeout"
echo "A channel:      $BASE_CHANNEL"
echo "B channel:      $TEST_CHANNEL"
echo

echo "current configured channel: $(configured_channel)"
echo "current actual channel:     $(actual_channel)"

[[ "$(configured_channel)" == "$BASE_CHANNEL" ]] || {
    echo "FAIL: expected production profile on channel $BASE_CHANNEL before A/B test" >&2
    exit 1
}
[[ "$(actual_channel)" == "$BASE_CHANNEL" ]] || {
    echo "FAIL: expected active AP on channel $BASE_CHANNEL before A/B test" >&2
    exit 1
}

RESTORE_REQUIRED=1
run_phase "A" "$BASE_CHANNEL"
run_phase "B" "$TEST_CHANNEL"

restore_channel6
wait_nodes_online || true

echo
echo "===== FINAL ====="
echo "restored configured channel: $(configured_channel)"
echo "restored actual channel:     $(actual_channel)"
echo "end:                         $(date --iso-8601=seconds)"
echo "log:                         $LOG"
echo "A/B TEST COMPLETE"
