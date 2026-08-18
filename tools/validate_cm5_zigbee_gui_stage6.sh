#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/validate_cm5_zigbee_gui_stage6.sh"
fi

section "PRECHECK SERVICES"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    if systemctl is-active --quiet "${unit}"; then
        echo "${unit}: active"
    else
        fail "${unit} is not active"
    fi
done

core_pid_before="$(systemctl show -p MainPID --value ventilation-core.service)"
[[ "${core_pid_before}" =~ ^[1-9][0-9]*$ ]] || fail "Unable to read ventilation-core MainPID"
echo "ventilation-core PID before: ${core_pid_before}"

section "STATIC VALIDATION"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_zigbee_gui_stage6.py' -v

section "RESTART WEB UI ONLY"
systemctl restart wvc-web-ui.service
for _ in $(seq 1 20); do
    if systemctl is-active --quiet wvc-web-ui.service; then
        break
    fi
    sleep 0.25
done
if ! systemctl is-active --quiet wvc-web-ui.service; then
    journalctl -u wvc-web-ui.service -n 120 --no-pager >&2 || true
    fail "wvc-web-ui.service failed after Stage 6 deployment"
fi
echo "wvc-web-ui.service: active"

WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n 1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"
echo "web UI: ${BASE_URL}"

section "WAIT FOR SETTINGS ROUTE"
settings_file="$(mktemp)"
js_file="$(mktemp)"
css_file="$(mktemp)"
api_file="$(mktemp)"
trap 'rm -f "${settings_file:-}" "${js_file:-}" "${css_file:-}" "${api_file:-}"' EXIT

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

ready=false
for _ in $(seq 1 30); do
    if fetch_url "${BASE_URL}/settings" "${settings_file}" 2>/dev/null; then
        ready=true
        break
    fi
    sleep 0.25
done
[[ "${ready}" == true ]] || fail "GET /settings did not become ready"

fetch_url "${BASE_URL}/zigbee-settings.js" "${js_file}" || fail "Unable to fetch zigbee-settings.js"
fetch_url "${BASE_URL}/zigbee-settings.css" "${css_file}" || fail "Unable to fetch zigbee-settings.css"
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}" || fail "Unable to fetch /api/v1/zigbee"

echo "GET /settings: PASS"
echo "zigbee-settings.js: PASS"
echo "zigbee-settings.css: PASS"

section "VALIDATE GUI CONTRACT"
python3 - "${settings_file}" "${js_file}" "${api_file}" <<'PY'
import json
import sys
from pathlib import Path

settings = Path(sys.argv[1]).read_text(encoding="utf-8")
script = Path(sys.argv[2]).read_text(encoding="utf-8")
payload = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))

if "USTAWIENIA" not in settings or "/dashboard-live.js" not in settings:
    raise SystemExit("ERROR: /settings is not serving the V2 shell")
if 'fetch("/api/v1/zigbee"' not in script:
    raise SystemExit("ERROR: Zigbee GUI does not read the dedicated API")
for forbidden in ("permit_join", "zigbee2mqtt/", 'method: "POST"'):
    if forbidden in script:
        raise SystemExit(f"ERROR: forbidden Zigbee write/direct MQTT surface found: {forbidden}")

if payload.get("ok") is not True:
    raise SystemExit("ERROR: /api/v1/zigbee returned ok=false")
zigbee = payload.get("zigbee")
if not isinstance(zigbee, dict) or zigbee.get("connected") is not True:
    raise SystemExit("ERROR: Zigbee MQTT is not connected through ventilation-core")

devices = zigbee.get("devices")
if not isinstance(devices, list):
    raise SystemExit("ERROR: devices is not a list")
expected = {
    "supply": ("temp_nawiew", "0xa4c13810e66fffff"),
    "extract": ("temp_wywiew", "0xa4c13810bdedffff"),
}
seen = {}
for device in devices:
    role = device.get("role")
    if role in expected:
        seen[role] = (device.get("friendly_name"), device.get("ieee_address"))
        if not isinstance(device.get("temperature_celsius"), (int, float)):
            raise SystemExit(f"ERROR: {role} has no temperature")
        if device.get("parse_errors") != 0:
            raise SystemExit(f"ERROR: {role} has parse_errors={device.get('parse_errors')!r}")
if seen != expected:
    raise SystemExit(f"ERROR: unexpected Zigbee mapping: {seen!r}")

print("route shell: PASS")
print("read-only API client: PASS")
print("mqtt connected: True")
for device in devices:
    if device.get("role") in expected:
        print(
            f"{device['role']}: {device['friendly_name']} "
            f"temperature={device['temperature_celsius']} "
            f"battery={device.get('battery_percent')} "
            f"lqi={device.get('linkquality')}"
        )
PY

section "CORE RESTART GUARD"
core_pid_after="$(systemctl show -p MainPID --value ventilation-core.service)"
echo "ventilation-core PID after:  ${core_pid_after}"
if [[ "${core_pid_after}" != "${core_pid_before}" ]]; then
    fail "ventilation-core restarted during Stage 6 validation"
fi
echo "ventilation-core untouched: PASS"

section "REGRESSION CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 6 PASS: Ustawienia -> Zigbee is available in Web V2 and reads only /api/v1/zigbee."
echo "No Zigbee write controls, alert changes or ventilation control changes were introduced."
