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
  sudo bash tools/validate_cm5_zigbee_stage7.sh
  sudo bash tools/validate_cm5_zigbee_stage7.sh --allow-hardware-offline

--allow-hardware-offline
  Use when the execution hardware is intentionally disconnected and only the
  CM5/Zigbee stack is under validation. Software setpoints must still be 0 V / 0 V.
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
    fail "Run as root: sudo bash tools/validate_cm5_zigbee_stage7.sh [--allow-hardware-offline]"
fi

section "GIT PRECHECK"
branch="$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
[[ "${branch}" == "agent/zigbee-stage1" ]] || fail "Expected agent/zigbee-stage1, got ${branch}"
if [[ -n "$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" status --porcelain)" ]]; then
    git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" status --short >&2
    fail "Working tree is not clean"
fi
head_sha="$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse HEAD)"
echo "branch: ${branch}"
echo "HEAD:   ${head_sha}"
echo "working tree: clean"

section "SERVICE PRECHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    if systemctl is-active --quiet "${unit}"; then
        echo "${unit}: active"
    else
        fail "${unit} is not active"
    fi
done
core_pid_before="$(systemctl show -p MainPID --value ventilation-core.service)"
web_pid_before="$(systemctl show -p MainPID --value wvc-web-ui.service)"
[[ "${core_pid_before}" =~ ^[1-9][0-9]*$ ]] || fail "Unable to read ventilation-core MainPID"
[[ "${web_pid_before}" =~ ^[1-9][0-9]*$ ]] || fail "Unable to read wvc-web-ui MainPID"
echo "ventilation-core PID: ${core_pid_before}"
echo "wvc-web-ui PID:       ${web_pid_before}"

section "SAFE STATE PRECHECK"
state_file="$(mktemp)"
bridge_file="$(mktemp)"
api_file="$(mktemp)"
web_state_file="$(mktemp)"
settings_file="$(mktemp)"
js_file="$(mktemp)"
css_file="$(mktemp)"
trap 'rm -f "${state_file:-}" "${bridge_file:-}" "${api_file:-}" "${web_state_file:-}" "${settings_file:-}" "${js_file:-}" "${css_file:-}"' EXIT

PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" \
    || fail "Unable to read ventilation-core state"
python3 - "${state_file}" "${ALLOW_HARDWARE_OFFLINE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
offline = sys.argv[2].lower() == "true"
if payload.get("ok") is not True:
    raise SystemExit("ERROR: ventilation-core status returned ok=false")
state = payload["state"]
setpoints = state.get("setpoints") or {}
if float(setpoints.get("supply_voltage", -1)) != 0.0 or float(setpoints.get("extract_voltage", -1)) != 0.0:
    raise SystemExit(f"ERROR: software setpoints are not 0 V / 0 V: {setpoints!r}")

if offline:
    alarms = state.get("active_alarms") or []
    has_dac_fault = any(a.get("code") == "DAC_COMMUNICATION_LOST" for a in alarms)
    if state.get("mode") != "FAULT":
        raise SystemExit(f"ERROR: standalone CM5 expected mode=FAULT, got {state.get('mode')!r}")
    if state.get("hardware_ready") is not False or state.get("output_state_known") is not False:
        raise SystemExit("ERROR: standalone CM5 expected hardware_ready=false and output_state_known=false")
    if not has_dac_fault:
        raise SystemExit("ERROR: standalone CM5 expected active DAC_COMMUNICATION_LOST")
    print("standalone CM5 / execution hardware intentionally offline: PASS")
    print("software setpoints: 0 V / 0 V")
else:
    if state.get("mode") != "STOP":
        raise SystemExit(f"ERROR: expected mode=STOP, got {state.get('mode')!r}")
    if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
        raise SystemExit("ERROR: production hardware state is not confirmed safe")
    print("production STOP / 0 V / hardware ready: PASS")
PY

section "ZIGBEE NETWORK PRECHECK"
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/bridge/info' -C 1 -W 5 >"${bridge_file}" \
    || fail "Unable to read retained zigbee2mqtt/bridge/info"
python3 - "${bridge_file}" <<'PY'
import json
import sys
from pathlib import Path

info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if info.get("permit_join") is not False:
    raise SystemExit(f"ERROR: permit_join must be false, got {info.get('permit_join')!r}")
coordinator = info.get("coordinator") or {}
if coordinator.get("type") != "ZStack3x0":
    raise SystemExit(f"ERROR: unexpected coordinator type: {coordinator.get('type')!r}")
if coordinator.get("ieee_address") != "0x00124b0038aaf159":
    raise SystemExit(f"ERROR: unexpected coordinator IEEE: {coordinator.get('ieee_address')!r}")
print("permit_join: false")
print("coordinator: ZStack3x0")
print("coordinator ieee: 0x00124b0038aaf159")
PY

section "PYTHON RUNTIME"
python3 - <<'PY'
from importlib.metadata import version
import paho.mqtt.client as mqtt
print("paho-mqtt:", version("paho-mqtt"))
print("callback API:", mqtt.CallbackAPIVersion.VERSION2)
PY

section "FULL REPOSITORY TEST SUITE"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_*.py' -v

echo "full unittest suite: PASS"

WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n 1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"

fetch_url() {
    python3 - "$1" "$2" <<'PY'
import sys
import urllib.request
url, target = sys.argv[1:3]
with urllib.request.urlopen(url, timeout=3.0) as response:
    body = response.read()
    if response.status != 200:
        raise SystemExit(1)
open(target, "wb").write(body)
PY
}

section "LIVE END-TO-END STATE"
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}" || fail "Unable to fetch /api/v1/zigbee"
fetch_url "${BASE_URL}/api/v1/state" "${web_state_file}" || fail "Unable to fetch /api/v1/state"
fetch_url "${BASE_URL}/settings" "${settings_file}" || fail "Unable to fetch /settings"
fetch_url "${BASE_URL}/zigbee-settings.js" "${js_file}" || fail "Unable to fetch zigbee-settings.js"
fetch_url "${BASE_URL}/zigbee-settings.css" "${css_file}" || fail "Unable to fetch zigbee-settings.css"

python3 - "${state_file}" "${api_file}" "${web_state_file}" "${settings_file}" "${js_file}" <<'PY'
import json
import sys
from pathlib import Path

ctl_payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
api_payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
web_state_payload = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
settings = Path(sys.argv[4]).read_text(encoding="utf-8")
script = Path(sys.argv[5]).read_text(encoding="utf-8")

if api_payload.get("ok") is not True:
    raise SystemExit("ERROR: /api/v1/zigbee returned ok=false")
zigbee = api_payload.get("zigbee")
if not isinstance(zigbee, dict) or zigbee.get("running") is not True or zigbee.get("connected") is not True:
    raise SystemExit("ERROR: ventilation-core Zigbee MQTT monitor is not running/connected")

ctl_zigbee = (ctl_payload.get("state") or {}).get("zigbee")
web_zigbee = (web_state_payload.get("state") or {}).get("zigbee")
if zigbee != web_zigbee:
    raise SystemExit("ERROR: /api/v1/zigbee differs from /api/v1/state state.zigbee")

expected = {
    "supply": ("temp_nawiew", "0xa4c13810e66fffff"),
    "extract": ("temp_wywiew", "0xa4c13810bdedffff"),
}
seen = {}
for device in zigbee.get("devices") or []:
    role = device.get("role")
    if role not in expected:
        continue
    seen[role] = (device.get("friendly_name"), device.get("ieee_address"))
    if not isinstance(device.get("temperature_celsius"), (int, float)):
        raise SystemExit(f"ERROR: {role} has no numeric temperature")
    if not isinstance(device.get("battery_percent"), (int, float)):
        raise SystemExit(f"ERROR: {role} has no numeric battery")
    if not isinstance(device.get("linkquality"), int):
        raise SystemExit(f"ERROR: {role} has no integer linkquality")
    if not isinstance(device.get("messages"), int) or device["messages"] < 1:
        raise SystemExit(f"ERROR: {role} has no received messages")
    if device.get("parse_errors") != 0:
        raise SystemExit(f"ERROR: {role} parse_errors={device.get('parse_errors')!r}")
if seen != expected:
    raise SystemExit(f"ERROR: unexpected Zigbee device mapping: {seen!r}")

if "USTAWIENIA" not in settings or "/dashboard-live.js" not in settings:
    raise SystemExit("ERROR: /settings is not serving Web V2 shell")
if 'fetch("/api/v1/zigbee"' not in script:
    raise SystemExit("ERROR: Zigbee settings GUI does not read /api/v1/zigbee")
for forbidden in ("permit_join", "zigbee2mqtt/", 'method: "POST"'):
    if forbidden in script:
        raise SystemExit(f"ERROR: forbidden write/direct MQTT surface in Zigbee GUI: {forbidden}")

print("web API == web state.zigbee: PASS")
print("settings route/assets: PASS")
print("read-only GUI contract: PASS")
for device in zigbee["devices"]:
    if device.get("role") in expected:
        print(
            f"{device['role']}: {device['friendly_name']} "
            f"temp={device['temperature_celsius']} "
            f"battery={device['battery_percent']} "
            f"lqi={device['linkquality']} "
            f"messages={device['messages']} "
            f"parse_errors={device['parse_errors']}"
        )

# ctl status was captured before the full suite and may have older counters than
# the live Web snapshot. Verify identity/mapping, not exact message counters.
ctl_seen = {
    d.get("role"): (d.get("friendly_name"), d.get("ieee_address"))
    for d in (ctl_zigbee or {}).get("devices", [])
    if d.get("role") in expected
}
if ctl_seen != expected:
    raise SystemExit(f"ERROR: direct core state has unexpected mapping: {ctl_seen!r}")
print("direct core mapping: PASS")
PY

section "NO-RESTART GUARD"
core_pid_after="$(systemctl show -p MainPID --value ventilation-core.service)"
web_pid_after="$(systemctl show -p MainPID --value wvc-web-ui.service)"
echo "ventilation-core PID before/after: ${core_pid_before} / ${core_pid_after}"
echo "wvc-web-ui PID before/after:       ${web_pid_before} / ${web_pid_after}"
[[ "${core_pid_after}" == "${core_pid_before}" ]] || fail "ventilation-core restarted during Stage 7 validation"
[[ "${web_pid_after}" == "${web_pid_before}" ]] || fail "wvc-web-ui restarted during Stage 7 validation"
echo "services untouched: PASS"

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 7 PASS: Zigbee branch passed full regression and live end-to-end validation."
if [[ "${ALLOW_HARDWARE_OFFLINE}" == true ]]; then
    echo "Validation mode: standalone CM5 with execution hardware intentionally offline."
fi
echo "No services were restarted and no Zigbee write/control action was performed."
echo "agent/zigbee-stage1 is ready for later integration; main remains untouched."
