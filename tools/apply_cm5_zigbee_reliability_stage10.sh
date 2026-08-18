#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOW_HARDWARE_OFFLINE=false

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

usage() {
    cat <<'EOF'
Usage:
  sudo bash tools/apply_cm5_zigbee_reliability_stage10.sh
  sudo bash tools/apply_cm5_zigbee_reliability_stage10.sh --allow-hardware-offline
EOF
}

if [[ "${1:-}" == "--allow-hardware-offline" ]]; then
    ALLOW_HARDWARE_OFFLINE=true
    shift
fi
if [[ "$#" -ne 0 ]]; then
    usage >&2
    exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/apply_cm5_zigbee_reliability_stage10.sh [--allow-hardware-offline]"
fi

section "GIT PRECHECK"
branch="$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
[[ "${branch}" == "agent/zigbee-management-alerts-stage1" ]] || fail "Expected agent/zigbee-management-alerts-stage1, got ${branch}"
if [[ -n "$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" status --porcelain)" ]]; then
    git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" status --short >&2
    fail "Working tree is not clean"
fi
echo "branch: ${branch}"
echo "HEAD:   $(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse HEAD)"
echo "working tree: clean"

section "SERVICE PRECHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    systemctl is-active --quiet "${unit}" || fail "${unit} is not active"
    echo "${unit}: active"
done

state_file="$(mktemp)"
config_result="$(mktemp)"
bridge_info="$(mktemp)"
trap 'rm -f "${state_file:-}" "${config_result:-}" "${bridge_info:-}"' EXIT

section "SAFE STATE PRECHECK"
PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" \
    || fail "Unable to read ventilation-core state"
python3 - "${state_file}" "${ALLOW_HARDWARE_OFFLINE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
offline = sys.argv[2].lower() == "true"
state = payload["state"]
setpoints = state["setpoints"]
if float(setpoints["supply_voltage"]) != 0.0 or float(setpoints["extract_voltage"]) != 0.0:
    raise SystemExit(f"ERROR: software setpoints are not 0 V / 0 V: {setpoints!r}")
if offline:
    alarms = state.get("active_alarms") or []
    if state.get("mode") != "FAULT":
        raise SystemExit(f"ERROR: standalone CM5 expected FAULT, got {state.get('mode')!r}")
    if not any(a.get("code") == "DAC_COMMUNICATION_LOST" for a in alarms):
        raise SystemExit("ERROR: standalone CM5 expected DAC_COMMUNICATION_LOST")
    print("standalone CM5 / execution hardware intentionally offline: PASS")
else:
    if state.get("mode") != "STOP":
        raise SystemExit(f"ERROR: expected STOP, got {state.get('mode')!r}")
    if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
        raise SystemExit("ERROR: production hardware state is not confirmed safe")
    print("production STOP / hardware ready: PASS")
print("software setpoints: 0 V / 0 V")
PY

section "STATIC VALIDATION"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_zigbee_reliability_stage10.py' -v
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_*.py' >/dev/null
echo "full unittest suite: PASS"

section "ZIGBEE NETWORK PRECHECK"
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/bridge/info' -C 1 -W 5 >"${bridge_info}" \
    || fail "Unable to read retained bridge/info"
python3 - "${bridge_info}" <<'PY'
import json
import sys
from pathlib import Path
info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if info.get("permit_join") is not False:
    raise SystemExit(f"ERROR: permit_join must be false, got {info.get('permit_join')!r}")
print("permit_join: false")
print("coordinator:", (info.get("coordinator") or {}).get("type"))
PY

section "APPLY ZIGBEE2MQTT RELIABILITY POLICY"
python3 - "${config_result}" <<'PY'
import json
import sys
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt

result_path = Path(sys.argv[1])
base = "zigbee2mqtt"
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"wvc-stage10-{uuid.uuid4().hex[:10]}")
connected = threading.Event()
lock = threading.Lock()
pending = {}


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        return
    client.subscribe(f"{base}/bridge/response/#")
    connected.set()


def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except Exception:
        return
    transaction = payload.get("transaction") if isinstance(payload, dict) else None
    if transaction is None:
        return
    with lock:
        entry = pending.get(str(transaction))
    if entry is None:
        return
    event, box = entry
    box.update(payload)
    event.set()


client.on_connect = on_connect
client.on_message = on_message
client.connect("127.0.0.1", 1883, 30)
client.loop_start()
if not connected.wait(5.0):
    raise SystemExit("ERROR: MQTT configuration client did not connect")


def request(suffix, body, timeout=20.0):
    transaction = uuid.uuid4().hex
    event = threading.Event()
    box = {}
    with lock:
        pending[transaction] = (event, box)
    payload = {**body, "transaction": transaction}
    info = client.publish(
        f"{base}/bridge/request/{suffix}",
        json.dumps(payload, separators=(",", ":")),
        qos=0,
        retain=False,
    )
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise SystemExit(f"ERROR: publish {suffix} failed rc={info.rc}")
    if not event.wait(timeout):
        raise SystemExit(f"ERROR: timeout waiting for {suffix}")
    with lock:
        pending.pop(transaction, None)
    if box.get("status") != "ok":
        raise SystemExit(f"ERROR: {suffix} rejected: {box}")
    return box

responses = {}
for name in ("temp_nawiew", "temp_wywiew"):
    response = request("device/options", {"id": name, "options": {"retain": True}})
    to_options = ((response.get("data") or {}).get("to") or {})
    if to_options.get("retain") is not True:
        raise SystemExit(f"ERROR: retain=true not confirmed for {name}: {response}")
    responses[name] = response
    print(f"{name}: retain=true PASS")

availability = request("options", {"options": {"availability": {"enabled": True}}})
responses["availability"] = availability
print("availability.enabled=true request: PASS")
print("availability restart_required:", bool((availability.get("data") or {}).get("restart_required")))

result_path.write_text(json.dumps(responses, indent=2), encoding="utf-8")
client.disconnect()
client.loop_stop()
PY

section "RESTART ZIGBEE2MQTT FOR AVAILABILITY"
systemctl restart zigbee2mqtt.service
for _ in $(seq 1 80); do
    if systemctl is-active --quiet zigbee2mqtt.service; then
        if mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/bridge/state' -C 1 -W 1 2>/dev/null \
            | grep -q '"state":"online"'; then
            break
        fi
    fi
    sleep 0.25
done
systemctl is-active --quiet zigbee2mqtt.service || fail "zigbee2mqtt.service is not active after restart"
bridge_state="$(mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/bridge/state' -C 1 -W 5)"
[[ "${bridge_state}" == *'"state":"online"'* ]] || fail "Zigbee2MQTT bridge did not return online"
echo "zigbee2mqtt bridge online: PASS"

mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/bridge/info' -C 1 -W 5 >"${bridge_info}" \
    || fail "Unable to read bridge/info after restart"
python3 - "${bridge_info}" <<'PY'
import json
import sys
from pathlib import Path
info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
config = info.get("config") or {}
availability = config.get("availability") or {}
if availability.get("enabled") is not True:
    raise SystemExit(f"ERROR: bridge config does not confirm availability.enabled=true: {availability!r}")
print("bridge config availability.enabled: true")
PY

section "AVAILABILITY RETAINED TOPICS"
for name in temp_nawiew temp_wywiew; do
    payload="$(mosquitto_sub -h 127.0.0.1 -p 1883 -t "zigbee2mqtt/${name}/availability" -C 1 -W 10)" \
        || fail "No retained availability payload for ${name}"
    python3 - "${name}" "${payload}" <<'PY'
import json
import sys
name, raw = sys.argv[1:3]
payload = json.loads(raw)
if payload.get("state") not in {"online", "offline"}:
    raise SystemExit(f"ERROR: invalid availability payload for {name}: {payload!r}")
print(f"{name}: availability={payload['state']} retained topic PASS")
PY
done

section "REQUEST CURRENT SENSOR VALUES"
for name in temp_nawiew temp_wywiew; do
    mosquitto_pub -h 127.0.0.1 -p 1883 -t "zigbee2mqtt/${name}/get" -m '{"temperature":"","battery":""}' || true
done
echo "temperature/battery GET requested; sleeping battery devices may answer on their next wake-up"
sleep 2

section "RESTART CORE TO VERIFY RETAIN RESTORE"
systemctl restart ventilation-core.service
for _ in $(seq 1 80); do
    if systemctl is-active --quiet ventilation-core.service \
        && PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" 2>/dev/null; then
        if python3 - "${state_file}" <<'PY'
import json
import sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["state"]
z = state.get("zigbee") or {}
raise SystemExit(0 if z.get("connected") is True and z.get("bridge_online") is True else 1)
PY
        then
            break
        fi
    fi
    sleep 0.25
done
systemctl is-active --quiet ventilation-core.service || fail "ventilation-core.service is not active after restart"

PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}"
python3 - "${state_file}" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["state"]
z = state.get("zigbee") or {}
if z.get("connected") is not True or z.get("bridge_online") is not True:
    raise SystemExit("ERROR: core Zigbee MQTT/bridge is not online")

devices = {d.get("role"): d for d in z.get("devices") or []}
for role, expected_name in (("supply", "temp_nawiew"), ("extract", "temp_wywiew")):
    device = devices.get(role)
    if not device or device.get("friendly_name") != expected_name:
        raise SystemExit(f"ERROR: missing role {role}")
    available = device.get("available")
    if not isinstance(available, bool):
        raise SystemExit(f"ERROR: {expected_name} availability not decoded: {available!r}")
    restored = (
        isinstance(device.get("temperature_celsius"), (int, float))
        and isinstance(device.get("battery_percent"), (int, float))
        and isinstance(device.get("last_seen"), str)
        and bool(device.get("last_seen"))
    )
    print(
        f"{role}: {expected_name} availability={available} "
        f"temp={device.get('temperature_celsius')} battery={device.get('battery_percent')} "
        f"last_seen={device.get('last_seen')} messages={device.get('messages')} "
        f"retained_restore={'PASS' if restored else 'WAITING_FOR_FIRST_RETAINED_REPORT'}"
    )

print("stale-age source: device last_seen (fallback last_message_at)")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 10 configuration PASS: availability is enabled and both semantic sensors use retained MQTT state."
echo "Core now decodes Zigbee2MQTT JSON availability and evaluates stale data from device last_seen."
echo "If retained_restore is still WAITING for a battery sensor, wake/warm that sensor once; the next report will seed the retained topic for future core restarts."
