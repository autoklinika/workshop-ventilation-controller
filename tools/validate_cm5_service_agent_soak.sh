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
cleanup() {
    rm -rf "${tmp_dir}"
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
    raise SystemExit("unexpected registered node count")
if agent.get("online_nodes") != expected_nodes:
    raise SystemExit("not all service nodes are online")
if not isinstance(network, dict) or network.get("ready") is not True:
    raise SystemExit("service network is not ready")
for field in ("ap_active", "address_present", "dhcp_active", "firewall_active"):
    if network.get(field) is not True:
        raise SystemExit(f"network field {field} is not true")
if not isinstance(service_nodes, list) or len(service_nodes) != expected_nodes:
    raise SystemExit("service node list has unexpected size")

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

current = {}
for node in sensor_nodes:
    address = node.get("slave_address")
    current[str(address)] = {
        "polls": int(node.get("polls", -1)),
        "successful_polls": int(node.get("successful_polls", -1)),
        "communication_errors": int(node.get("communication_errors", -1)),
    }
    if node.get("online") is not True:
        raise SystemExit(f"slave {address} is offline")
    if node.get("usable") is not True:
        raise SystemExit(f"slave {address} is not usable")
    if node.get("measurement_valid") is not True:
        raise SystemExit(f"slave {address} measurement is invalid")
    if node.get("measurement_stale") is not False:
        raise SystemExit(f"slave {address} measurement is stale")
    if node.get("communication_errors") != 0:
        raise SystemExit(f"slave {address} has communication errors")
    if node.get("consecutive_failures") != 0:
        raise SystemExit(f"slave {address} has consecutive failures")
    if node.get("invalid_measurements") != 0:
        raise SystemExit(f"slave {address} has invalid measurements")
    if node.get("stale_measurements") != 0:
        raise SystemExit(f"slave {address} has stale measurements")
    if node.get("map_version_errors") != 0:
        raise SystemExit(f"slave {address} has map version errors")
    if node.get("polls") != node.get("successful_polls"):
        raise SystemExit(f"slave {address} polls and successful_polls differ")
    if address not in service_by_address:
        raise SystemExit(f"slave {address} has no matching service node")

if previous_path.exists():
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    for address, values in current.items():
        old = previous.get(address)
        if not isinstance(old, dict):
            raise SystemExit(f"missing previous state for slave {address}")
        if values["polls"] <= int(old["polls"]):
            raise SystemExit(f"slave {address} polls did not increase")
        if values["successful_polls"] <= int(old["successful_polls"]):
            raise SystemExit(f"slave {address} successful_polls did not increase")
        if values["communication_errors"] != int(old["communication_errors"]):
            raise SystemExit(f"slave {address} communication error count changed")

current_path.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
PY
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
    validate_snapshot \
        "${prefix}-service.json" \
        "${prefix}-sensors.json" \
        "${previous_state}" \
        "${last_state}"

    if [[ ! -e "${baseline_state}" ]]; then
        cp "${last_state}" "${baseline_state}"
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
        f"communication_errors={end['communication_errors']}"
    )
PY

pass "service agent and SENSOR BUS soak completed"
pass "ventilation-core PID remained ${core_pid}"
pass "network isolation checks passed before and after soak"
