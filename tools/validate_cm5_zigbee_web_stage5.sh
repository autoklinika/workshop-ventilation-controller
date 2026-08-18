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
    fail "Run as root: sudo bash tools/validate_cm5_zigbee_web_stage5.sh"
fi

section "PRECHECK SERVICES"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    if systemctl is-active --quiet "${unit}"; then
        echo "${unit}: active"
    else
        fail "${unit} is not active"
    fi
done

section "STATIC VALIDATION"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_zigbee_web_api_stage5.py' -v

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
    fail "wvc-web-ui.service failed after Stage 5 deployment"
fi
echo "wvc-web-ui.service: active"

WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n 1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"

echo "web API: ${BASE_URL}"

section "WAIT FOR ZIGBEE WEB API"
api_file="$(mktemp)"
state_file="$(mktemp)"
trap 'rm -f "${api_file:-}" "${state_file:-}"' EXIT
ready=false
for _ in $(seq 1 30); do
    if python3 - "${BASE_URL}/api/v1/zigbee" "${api_file}" <<'PY' 2>/dev/null
import sys
import urllib.request

url, target = sys.argv[1:3]
with urllib.request.urlopen(url, timeout=2.0) as response:
    body = response.read()
if response.status != 200:
    raise SystemExit(1)
open(target, "wb").write(body)
PY
    then
        ready=true
        break
    fi
    sleep 0.25
done

if [[ "${ready}" != true ]]; then
    journalctl -u wvc-web-ui.service -n 120 --no-pager >&2 || true
    fail "GET /api/v1/zigbee did not become ready"
fi

section "VALIDATE ZIGBEE API CONTRACT"
python3 - "${api_file}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    raise SystemExit(f"ERROR: Zigbee endpoint returned ok={payload.get('ok')!r}")
zigbee = payload.get("zigbee")
if not isinstance(zigbee, dict):
    raise SystemExit("ERROR: missing zigbee object")
if zigbee.get("connected") is not True:
    raise SystemExit(f"ERROR: MQTT not connected in Web API: {zigbee.get('connected')!r}")

expected = {
    "supply": ("temp_nawiew", "0xa4c13810e66fffff"),
    "extract": ("temp_wywiew", "0xa4c13810bdedffff"),
}
seen = {}
for device in zigbee.get("devices") or []:
    seen[device.get("role")] = (device.get("friendly_name"), device.get("ieee_address"))
if seen != expected:
    raise SystemExit(f"ERROR: unexpected Zigbee device mapping: {seen!r}")

print("mqtt connected:", zigbee["connected"])
for device in zigbee["devices"]:
    print(
        f"{device['role']}: {device['friendly_name']} "
        f"temperature={device.get('temperature_celsius')} "
        f"battery={device.get('battery_percent')} "
        f"lqi={device.get('linkquality')} "
        f"messages={device.get('messages')} "
        f"parse_errors={device.get('parse_errors')}"
    )
PY

section "AUTHORITATIVE STATE CHECK"
python3 - "${BASE_URL}/api/v1/state" "${state_file}" <<'PY'
import sys
import urllib.request

url, target = sys.argv[1:3]
with urllib.request.urlopen(url, timeout=2.0) as response:
    body = response.read()
if response.status != 200:
    raise SystemExit(f"ERROR: GET /api/v1/state returned HTTP {response.status}")
open(target, "wb").write(body)
PY

python3 - "${api_file}" "${state_file}" <<'PY'
import json
import sys
from pathlib import Path

zigbee_payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
state_payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
zigbee_from_state = (state_payload.get("state") or {}).get("zigbee")
if zigbee_payload.get("zigbee") != zigbee_from_state:
    raise SystemExit("ERROR: /api/v1/zigbee differs from authoritative state.zigbee")
print("dedicated endpoint == state.zigbee: PASS")
PY

section "REGRESSION CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 5 PASS: Web API exposes authoritative read-only Zigbee state at /api/v1/zigbee."
echo "No Zigbee write endpoints, alert changes or ventilation control changes were introduced."
