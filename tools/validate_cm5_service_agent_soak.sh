#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DURATION_SECONDS="${1:-1800}"
INTERVAL_SECONDS="${2:-10}"
EXPECTED_NODES="${EXPECTED_NODES:-2}"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "run as root: sudo bash $0 [duration_seconds] [interval_seconds]"
fi

[[ "${DURATION_SECONDS}" =~ ^[0-9]+$ ]] || fail "duration must be an integer"
[[ "${INTERVAL_SECONDS}" =~ ^[0-9]+$ ]] || fail "interval must be an integer"
(( DURATION_SECONDS >= 60 )) || fail "duration must be at least 60 seconds"
(( INTERVAL_SECONDS >= 1 )) || fail "interval must be at least 1 second"
(( INTERVAL_SECONDS < DURATION_SECONDS )) || fail "interval must be shorter than duration"

tmp_dir="$(mktemp -d /tmp/wvc-service-agent-soak.XXXXXX)"
test_completed=false
cleanup() {
    local status=$?
    if [[ "${test_completed}" == true && ${status} -eq 0 ]]; then
        rm -rf "${tmp_dir}"
    else
        echo "Soak diagnostics preserved in: ${tmp_dir}" >&2
    fi
}
trap cleanup EXIT INT TERM

run_as_wentylacja() {
    sudo -u wentylacja env PYTHONPATH="${ROOT_DIR}/src" "$@"
}

capture_snapshot() {
    local prefix="$1"
    run_as_wentylacja python3 -m ventilation_core.service_ctl status \
        > "${prefix}-service.json"
    run_as_wentylacja python3 -m ventilation_core.ctl sensors \
        > "${prefix}-sensors.json"
}

validate_snapshot() {
    local service_path="$1"
    local sensors_path="$2"
    local previous_path="$3"
    local current_path="$4"

    python3 - \
        "${service_path}" \
        "${sensors_path}" \
        "${previous_path}" \
        "${current_path}" \
        "${EXPECTED_NODES}" <<'PY'
import json
import sys
from pathlib import Path

service_path = Path(sys.argv[1])
sensors_path = Path(sys.argv[2])
previous_path = Path(sys.argv[3])
current_path = Path(sys.argv[4])
expected_nodes = int(sys.argv[5])

service = json.loads(service_path.read_text(encoding="utf-8"))
sensors_document = json.loads(sensors_path.read_text(encoding="utf-8"))

if service.get("ok") is not True:
    raise SystemExit("service API returned ok=false")
agent = service.get("agent")
network = service.get("network")
service_nodes = service.get("nodes")
if not isinstance(agent, dict) or agent.get("ready") is not True:
    raise SystemExit("service agent is not ready")
if agent.get("registered_nodes") != expected_nodes:
    raise SystemExit(
        f"unexpected registered node count: {agent.get('registered_nodes')}"
    )
if not isinstance(service_nodes, list) or len(service_nodes) != expected_nodes:
    raise SystemExit("service node list has unexpected size")
if agent.get("online_nodes") != expected_nodes:
    details = []
    for node in service_nodes:
        heartbeat = node.get("heartbeat")
        heartbeat = heartbeat if isinstance(heartbeat, dict) else {}
        details.append(
            {
                "node_id": node.get("node_id"),
                "online": node.get("online"),
                "received_unix_ms": node.get("received_unix_ms"),
                "source_ip": node.get("source_ip"),
                "boot_id": heartbeat.get("boot_id"),
                "seq": heartbeat.get("seq"),
                "uptime_s": heartbeat.get("uptime_s"),
                "wifi_rssi_dbm": heartbeat.get("wifi_rssi_dbm"),
                "modbus_requests_total": heartbeat.get("modbus_requests_total"),
            }
        )
    raise SystemExit(
        "not all service nodes are online: "
        + json.dumps(details, sort_keys=True)
    )
if not isinstance(network, dict) or network.get("ready") is not True:
    raise SystemExit(
        "service network is not ready: "
        + json.dumps(network, sort_keys=True)
    )
for field in ("ap_active", "address_present", "dhcp_active", "firewall_active"):
    if network.get(field) is not True:
        raise SystemExit(f"network field {field} is not true")

service_by_address = {}
for node in service_nodes:
    address = node.get("modbus_address")
    if address in service_by_address:
        raise SystemExit("duplicate service node Modbus address")
    service_by_address[address] = node
    if node.get("online") is not True:
        raise SystemExit(f"service node {node.get('node_id')} is offline")
    if node.get("rs485_ready") is not True:
        raise SystemExit(f"service node {node.get('node_id')} RS-485 is not ready")
    if node.get("modbus_monitor_ready") is not True:
        raise SystemExit(f"service node {node.get('node_id')} monitor is not ready")

sensor_bus = sensors_document.get("sensor_bus")
if sensors_document.get("ok") is not True or not isinstance(sensor_bus, dict):
    raise SystemExit("SENSOR BUS API failed")
if sensor_bus.get("ready") is not True:
    raise SystemExit("SENSOR BUS is not ready")
if sensor_bus.get("worker_alive") is not True:
    raise SystemExit("SENSOR BUS worker is not alive")
if sensor_bus.get("worker_restarts") != 0:
    raise SystemExit("SENSOR BUS worker restarted")
if sensor_bus.get("last_error") is not None:
    raise SystemExit("SENSOR BUS reports last_error")

sensor_nodes = sensor_bus.get("nodes")
if not isinstance(sensor_nodes, list) or len(sensor_nodes) != expected_nodes:
    raise SystemExit("SENSOR BUS node list has unexpected size")

counter_fields = (
    "communication_errors",
    "invalid_measurements",
    "stale_measurements",
    "map_version_errors",
)
current = {}
for node in sensor_nodes:
    address = node.get("slave_address")
    values = {
        "polls": int(node.get("polls", -1)),
        "successful_polls": int(node.get("successful_polls", -1)),
    }
    for field in counter_fields:
        values[field] = int(node.get(field, -1))
    current[str(address)] = values

    if node.get("online") is not True:
        raise SystemExit(f"slave {address} is offline")
    if node.get("usable") is not True:
        raise SystemExit(f"slave {address} is not usable")
    if node.get("measurement_valid") is not True:
        raise SystemExit(f"slave {address} measurement is invalid")
    if node.get("measurement_stale") is not False:
        raise SystemExit(f"slave {address} measurement is stale")
    if node.get("consecutive_failures") != 0:
        raise SystemExit(f"slave {address} has consecutive failures")
    if any(value < 0 for value in values.values()):
        raise SystemExit(f"slave {address} exposes an invalid counter value")
    if address not in service_by_address:
        raise SystemExit(f"slave {address} has no matching service node")

if previous_path.exists():
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    for address, values in current.items():
        old = previous.get(address)
        if not isinstance(old, dict):
            raise SystemExit(f"missing previous state for slave {address}")

        poll_delta = values["polls"] - int(old["polls"])
        success_delta = values["successful_polls"] - int(old["successful_polls"])
        if poll_delta <= 0:
            raise SystemExit(f"slave {address} polls did not increase")
        if success_delta <= 0:
            raise SystemExit(f"slave {address} successful_polls did not increase")
        if poll_delta != success_delta:
            raise SystemExit(
                f"slave {address} acquired a non-successful poll during soak: "
                f"poll_delta={poll_delta} success_delta={success_delta}"
            )

        for field in counter_fields:
            if values[field] != int(old[field]):
                raise SystemExit(
                    f"slave {address} counter {field} changed "
                    f"{old[field]} -> {values[field]}"
                )

current_path.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
PY
}

collect_failure_diagnostics() {
    local prefix="$1"
    local sample="$2"

    {
        echo "failure_sample=${sample}"
        echo "captured_at=$(date --iso-8601=seconds)"
        echo "ventilation_core_pid=$(systemctl show -p MainPID --value ventilation-core.service)"
        echo "service_agent_pid=$(systemctl show -p MainPID --value wvc-service-agent.service)"
    } > "${prefix}-failure-summary.txt"

    journalctl -u wvc-service-agent.service \
        --since "@${start_epoch}" --no-pager -o short-iso \
        > "${prefix}-service-agent-journal.txt" 2>&1 || true
    journalctl -k --since "@${start_epoch}" --no-pager -o short-iso \
        > "${prefix}-kernel-journal.txt" 2>&1 || true
    iw dev wlan0 station dump \
        > "${prefix}-iw-station-dump.txt" 2>&1 || true
    ip -4 neighbor show dev wlan0 \
        > "${prefix}-ip-neighbor.txt" 2>&1 || true
    nmcli -f GENERAL,IP4 device show wlan0 \
        > "${prefix}-nmcli-wlan0.txt" 2>&1 || true
    cat /var/lib/misc/dnsmasq-wvc.leases \
        > "${prefix}-dnsmasq-leases.txt" 2>&1 || true

    echo "Failure diagnostics: ${tmp_dir}" >&2
    [[ -f "${prefix}-validation-error.txt" ]] \
        && cat "${prefix}-validation-error.txt" >&2
    echo "Current service snapshot:" >&2
    cat "${prefix}-service.json" >&2 || true
    echo "Current SENSOR BUS snapshot:" >&2
    cat "${prefix}-sensors.json" >&2 || true
    echo "Recent service-agent transitions:" >&2
    grep -E 'heartbeat (online|offline)|rejected heartbeat|service agent|sequence gap' \
        "${prefix}-service-agent-journal.txt" >&2 || true
}

systemctl is-active --quiet ventilation-core.service \
    || fail "ventilation-core is not active"
systemctl is-active --quiet wvc-service-agent.service \
    || fail "service agent is not active"

bash "${ROOT_DIR}/tools/validate_cm5_service_agent.sh"

core_pid="$(systemctl show -p MainPID --value ventilation-core.service)"
[[ -n "${core_pid}" && "${core_pid}" != "0" ]] \
    || fail "ventilation-core MainPID is invalid"

start_epoch="$(date +%s)"
end_epoch="$((start_epoch + DURATION_SECONDS))"
sample=0
previous_state="${tmp_dir}/previous.json"
baseline_state="${tmp_dir}/baseline.json"
last_state="${tmp_dir}/last.json"

printf 'Starting CM5 Service Agent soak test: duration=%ss interval=%ss PID=%s\n' \
    "${DURATION_SECONDS}" "${INTERVAL_SECONDS}" "${core_pid}"

while (( $(date +%s) < end_epoch )); do
    sample=$((sample + 1))
    prefix="${tmp_dir}/sample-${sample}"

    systemctl is-active --quiet ventilation-core.service \
        || fail "ventilation-core stopped at sample ${sample}"
    systemctl is-active --quiet wvc-service-agent.service \
        || fail "service agent stopped at sample ${sample}"

    current_pid="$(systemctl show -p MainPID --value ventilation-core.service)"
    [[ "${current_pid}" == "${core_pid}" ]] \
        || fail "ventilation-core PID changed ${core_pid} -> ${current_pid}"

    capture_snapshot "${prefix}"
    if ! validate_snapshot \
        "${prefix}-service.json" \
        "${prefix}-sensors.json" \
        "${previous_state}" \
        "${last_state}" \
        2> "${prefix}-validation-error.txt"; then
        collect_failure_diagnostics "${prefix}" "${sample}"
        exit 1
    fi

    if [[ ! -e "${baseline_state}" ]]; then
        cp "${last_state}" "${baseline_state}"
        echo "PASS: historical SENSOR BUS counters accepted as soak baseline"
        cat "${baseline_state}"
    fi
    cp "${last_state}" "${previous_state}"

    remaining="$((end_epoch - $(date +%s)))"
    (( remaining < 0 )) && remaining=0
    printf 'PASS: sample=%d remaining=%ss\n' "${sample}" "${remaining}"

    if (( remaining > 0 )); then
        sleep_for="${INTERVAL_SECONDS}"
        (( sleep_for > remaining )) && sleep_for="${remaining}"
        sleep "${sleep_for}"
    fi
done

bash "${ROOT_DIR}/tools/validate_cm5_service_agent.sh"

python3 - "${baseline_state}" "${last_state}" "${sample}" <<'PY'
import json
import sys
from pathlib import Path

baseline = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
last = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
samples = int(sys.argv[3])

print(f"Samples completed: {samples}")
for address in sorted(last, key=int):
    start = baseline[address]
    end = last[address]
    print(
        f"slave {address}: "
        f"polls {start['polls']} -> {end['polls']} "
        f"(delta {end['polls'] - start['polls']}), "
        f"successful {start['successful_polls']} -> {end['successful_polls']}, "
        f"communication_errors={start['communication_errors']} "
        f"(unchanged)"
    )
PY

pass "service agent and SENSOR BUS soak completed"
pass "ventilation-core PID remained ${core_pid}"
pass "no cumulative SENSOR BUS error counter increased during soak"
pass "network isolation checks passed before and after soak"
test_completed=true
