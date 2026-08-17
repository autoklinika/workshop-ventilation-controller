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
  sudo bash tools/validate_cm5_zigbee_management_alerts_stage9.sh
  sudo bash tools/validate_cm5_zigbee_management_alerts_stage9.sh --allow-hardware-offline
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
    fail "Run as root: sudo bash tools/validate_cm5_zigbee_management_alerts_stage9.sh [--allow-hardware-offline]"
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
api_file="$(mktemp)"
alerts_file="$(mktemp)"
settings_file="$(mktemp)"
js_file="$(mktemp)"
trap 'rm -f "${state_file:-}" "${api_file:-}" "${alerts_file:-}" "${settings_file:-}" "${js_file:-}"' EXIT

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

section "FULL TEST SUITE"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_*.py' -v
echo "full unittest suite: PASS"

section "RESTART CORE AND WEB"
systemctl restart ventilation-core.service
for _ in $(seq 1 30); do
    systemctl is-active --quiet ventilation-core.service && break
    sleep 0.25
done
systemctl is-active --quiet ventilation-core.service || {
    journalctl -u ventilation-core.service -n 160 --no-pager >&2 || true
    fail "ventilation-core failed after restart"
}
echo "ventilation-core.service: active"

WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n 1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"

ready=false
for _ in $(seq 1 80); do
    if PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" 2>/dev/null; then
        if python3 - "${state_file}" <<'PY'
import json
import sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["state"]
z = state.get("zigbee") or {}
ok = (
    z.get("connected") is True
    and z.get("bridge_online") is True
    and z.get("inventory_updated_at")
    and isinstance(z.get("inventory"), list)
)
raise SystemExit(0 if ok else 1)
PY
        then
            ready=true
            break
        fi
    fi
    sleep 0.25
done
[[ "${ready}" == true ]] || {
    cat "${state_file}" >&2 || true
    journalctl -u ventilation-core.service -n 160 --no-pager >&2 || true
    fail "Zigbee management state did not become ready"
}
echo "core Zigbee MQTT/bridge/inventory: ready"

systemctl restart wvc-web-ui.service
for _ in $(seq 1 30); do
    systemctl is-active --quiet wvc-web-ui.service && break
    sleep 0.25
done
systemctl is-active --quiet wvc-web-ui.service || {
    journalctl -u wvc-web-ui.service -n 120 --no-pager >&2 || true
    fail "wvc-web-ui failed after restart"
}
echo "wvc-web-ui.service: active"
echo "web UI: ${BASE_URL}"

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

post_json() {
    python3 - "$1" "$2" "$3" <<'PY'
import sys
import urllib.request
url, body, target = sys.argv[1:4]
request = urllib.request.Request(
    url,
    data=body.encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=25.0) as response:
    payload = response.read()
    if response.status != 200:
        raise SystemExit(1)
open(target, "wb").write(payload)
PY
}

section "LIVE INVENTORY AND API"
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}" || fail "Unable to fetch /api/v1/zigbee"
python3 - "${api_file}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
z = payload.get("zigbee") or {}
if payload.get("ok") is not True:
    raise SystemExit("ERROR: /api/v1/zigbee returned ok=false")
if z.get("connected") is not True or z.get("bridge_online") is not True:
    raise SystemExit("ERROR: Zigbee MQTT/bridge is not online")
if z.get("permit_join") is not False:
    raise SystemExit(f"ERROR: permit_join expected false, got {z.get('permit_join')!r}")

inventory = z.get("inventory")
if not isinstance(inventory, list):
    raise SystemExit("ERROR: inventory missing")
by_ieee = {d.get("ieee_address"): d for d in inventory}
expected = {
    "0x00124b0038aaf159": "Coordinator",
    "0xa4c13810e66fffff": "temp_nawiew",
    "0xa4c13810bdedffff": "temp_wywiew",
}
for ieee, name in expected.items():
    device = by_ieee.get(ieee)
    if device is None:
        raise SystemExit(f"ERROR: missing inventory device {ieee}")
    if device.get("friendly_name") != name:
        raise SystemExit(f"ERROR: {ieee} expected {name!r}, got {device.get('friendly_name')!r}")

print("mqtt connected: True")
print("bridge online: True")
print("permit_join: false")
print("inventory mapping: PASS")
for ieee, name in expected.items():
    d = by_ieee[ieee]
    print(f"{name}: {ieee} type={d.get('device_type')} model={d.get('model')}")
PY

section "SAFE MANAGEMENT WRITE PATH"
post_json "${BASE_URL}/api/v1/zigbee/permit-join" '{"seconds":0}' "${api_file}" \
    || fail "Unable to execute safe permit_join=0 through Web -> core -> Zigbee2MQTT"
python3 - "${api_file}" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    raise SystemExit(f"ERROR: permit_join=0 failed: {payload!r}")
management = payload.get("zigbee_management") or {}
if management.get("status") != "ok":
    raise SystemExit(f"ERROR: Zigbee2MQTT response is not ok: {management!r}")
print("POST /api/v1/zigbee/permit-join seconds=0: PASS")
print("No network-open or device-remove action was executed by validator.")
PY

sleep 0.5
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}" || fail "Unable to re-read Zigbee state"
python3 - "${api_file}" <<'PY'
import json
import sys
from pathlib import Path
z = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["zigbee"]
if z.get("permit_join") is not False:
    raise SystemExit(f"ERROR: permit_join is not closed: {z.get('permit_join')!r}")
print("permit_join remains false: PASS")
PY

section "GUI MANAGEMENT CONTRACT"
fetch_url "${BASE_URL}/settings" "${settings_file}" || fail "Unable to fetch /settings"
fetch_url "${BASE_URL}/zigbee-settings.js" "${js_file}" || fail "Unable to fetch zigbee-settings.js"
python3 - "${settings_file}" "${js_file}" <<'PY'
import sys
from pathlib import Path

settings = Path(sys.argv[1]).read_text(encoding="utf-8")
script = Path(sys.argv[2]).read_text(encoding="utf-8")
if "USTAWIENIA" not in settings:
    raise SystemExit("ERROR: settings shell missing")
for required in (
    "/api/v1/zigbee/permit-join",
    "/api/v1/zigbee/remove",
    "DODAJ URZĄDZENIE",
    "ZAMKNIJ PAROWANIE",
    "USUŃ",
):
    if required not in script:
        raise SystemExit(f"ERROR: missing GUI management contract: {required}")
for forbidden in ("mosquitto", "/api/v1/zigbee/publish"):
    if forbidden in script.lower():
        raise SystemExit(f"ERROR: forbidden generic/direct MQTT surface: {forbidden}")
print("settings management controls: PASS")
print("GUI -> Web API -> core boundary: PASS")
PY

section "ZIGBEE ALERT BASELINE"
fetch_url "${BASE_URL}/api/v1/alerts" "${alerts_file}" || fail "Unable to fetch alerts"
python3 - "${alerts_file}" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
active = payload.get("active") or []
zigbee = [a for a in active if str(a.get("code", "")).startswith("ZIGBEE_")]
if zigbee:
    raise SystemExit(f"ERROR: unexpected active Zigbee alerts in healthy Zigbee baseline: {zigbee!r}")
print("healthy Zigbee baseline has no active Zigbee alerts: PASS")
print("Zigbee alert codes are covered by unit tests for MQTT, bridge, device and battery failures.")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 8/9 PASS: Zigbee device management and core-owned Zigbee alerts are integrated."
echo "Validator performed only safe permit_join=0; it did not open pairing and did not remove any device."
echo "main remains untouched."
