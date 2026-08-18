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
    fail "Run as root: sudo bash tools/resume_cm5_zigbee_management_alerts_stage9_after_web_race.sh"
fi

section "GIT PRECHECK"
branch="$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
[[ "${branch}" == "agent/zigbee-management-alerts-stage1" ]] || fail "Expected agent/zigbee-management-alerts-stage1, got ${branch}"
echo "branch: ${branch}"
echo "HEAD:   $(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse HEAD)"

section "SERVICE PRECHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    systemctl is-active --quiet "${unit}" || fail "${unit} is not active"
    echo "${unit}: active"
done

WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n 1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"
echo "web UI: ${BASE_URL}"

api_file="$(mktemp)"
alerts_file="$(mktemp)"
settings_file="$(mktemp)"
js_file="$(mktemp)"
trap 'rm -f "${api_file:-}" "${alerts_file:-}" "${settings_file:-}" "${js_file:-}"' EXIT

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

section "WAIT FOR WEB LISTENER"
ready=false
for _ in $(seq 1 80); do
    if fetch_url "${BASE_URL}/api/v1/health" "${api_file}" 2>/dev/null; then
        ready=true
        break
    fi
    sleep 0.25
done
if [[ "${ready}" != true ]]; then
    journalctl -u wvc-web-ui.service -n 120 --no-pager >&2 || true
    fail "Web UI did not bind ${BASE_URL}"
fi
echo "web listener ready: PASS"

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
    d = by_ieee.get(ieee)
    if d is None:
        raise SystemExit(f"ERROR: missing inventory device {ieee}")
    if d.get("friendly_name") != name:
        raise SystemExit(f"ERROR: {ieee} expected {name!r}, got {d.get('friendly_name')!r}")
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
print("No network-open or device-remove action was executed.")
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
    raise SystemExit(f"ERROR: unexpected active Zigbee alerts in healthy baseline: {zigbee!r}")
print("healthy Zigbee baseline has no active Zigbee alerts: PASS")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 8/9 RESUME PASS: live management/API/GUI/alert validation completed after Web startup race."
echo "No services were restarted by this resume validator."
echo "No pairing-open or device-remove action was performed."
