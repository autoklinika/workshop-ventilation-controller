#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOW_HARDWARE_OFFLINE=false

fail(){ echo "ERROR: $*" >&2; exit 1; }
section(){ printf '\n===== %s =====\n' "$1"; }

if [[ "${1:-}" == "--allow-hardware-offline" ]]; then
    ALLOW_HARDWARE_OFFLINE=true
    shift
fi
[[ "$#" -eq 0 ]] || fail "Usage: sudo bash tools/validate_cm5_zigbee_sensor_list_stage14.sh [--allow-hardware-offline]"
[[ "${EUID}" -eq 0 ]] || fail "Run with sudo"

section "GIT PRECHECK"
branch="$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
[[ "${branch}" == "agent/zigbee-management-alerts-stage1" ]] || fail "Expected agent/zigbee-management-alerts-stage1, got ${branch}"
[[ -z "$(git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" status --porcelain)" ]] || fail "Working tree is not clean"
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
js_file="$(mktemp)"
trap 'rm -f "${state_file:-}" "${api_file:-}" "${js_file:-}"' EXIT

section "SAFE STATE PRECHECK"
PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}"
python3 - "${state_file}" "${ALLOW_HARDWARE_OFFLINE}" <<'PY'
import json,sys
from pathlib import Path
state=json.loads(Path(sys.argv[1]).read_text())["state"]
offline=sys.argv[2].lower()=="true"
sp=state["setpoints"]
if float(sp["supply_voltage"]) != 0.0 or float(sp["extract_voltage"]) != 0.0:
    raise SystemExit(f"ERROR: software outputs are not 0 V / 0 V: {sp!r}")
if offline:
    if state.get("mode") not in {"STOP","FAULT"}:
        raise SystemExit(f"ERROR: standalone CM5 expected STOP/FAULT, got {state.get('mode')!r}")
    print(f"standalone CM5 safe mode: {state.get('mode')} PASS")
else:
    if state.get("mode") != "STOP" or state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
        raise SystemExit("ERROR: production hardware state is not confirmed safe")
    print("production STOP / hardware ready: PASS")
print("software setpoints: 0 V / 0 V")
PY

section "STATIC VALIDATION"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest -v \
    tests.test_zigbee_sensor_list_stage14 \
    tests.test_zigbee_pairing_capabilities_stage13 \
    tests.test_zigbee_pairing_hydration_stage13 \
    tests.test_zigbee_core_confirmation_stage12 \
    tests.test_zigbee_role_management_stage11 \
    tests.test_zigbee_gui_stage6
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_*.py' -q
echo "full unittest suite: PASS"

section "RESTART CORE"
systemctl restart ventilation-core.service
ready=false
for _ in $(seq 1 120); do
    if PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" 2>/dev/null; then
        if python3 - "${state_file}" <<'PY'
import json,sys
from pathlib import Path
z=(json.loads(Path(sys.argv[1]).read_text())["state"].get("zigbee") or {})
inv={d.get("ieee_address") for d in z.get("inventory", [])}
rows={d.get("ieee_address") for d in z.get("sensor_list", [])}
expected={"0xa4c13810e66fffff","0xa4c13810bdedffff","0xa4c13879a816c919"}
ok=z.get("connected") is True and z.get("bridge_online") is True and expected.issubset(inv) and expected.issubset(rows)
raise SystemExit(0 if ok else 1)
PY
        then ready=true; break; fi
    fi
    sleep 0.25
done
[[ "${ready}" == true ]] || fail "ventilation-core did not restore complete Zigbee sensor list in time"
echo "ventilation-core sensor list: ready"

section "CORE SENSOR LIST"
python3 - "${state_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["state"]["zigbee"]
rows={d.get("ieee_address"):d for d in z.get("sensor_list", [])}
expected={
    "0xa4c13810e66fffff":("temp_nawiew","supply"),
    "0xa4c13810bdedffff":("temp_wywiew","extract"),
    "0xa4c13879a816c919":("temp_zew",None),
}
for ieee,(expected_name,expected_role) in expected.items():
    row=rows.get(ieee)
    if row is None:
        raise SystemExit(f"ERROR: missing sensor row {ieee}")
    if row.get("friendly_name") != expected_name:
        raise SystemExit(f"ERROR: unexpected name for {ieee}: {row.get('friendly_name')!r}")
    role=row.get("role")
    if expected_role is not None and role != expected_role:
        raise SystemExit(f"ERROR: unexpected role for {expected_name}: {role!r}")
    if expected_role is None and role not in (None,"other"):
        raise SystemExit(f"ERROR: temp_zew role must be BEZ ROLI or INNE, got {role!r}")
    print(
        f"{expected_name}: role={role or 'none'} temp={row.get('temperature_celsius')} "
        f"humidity={row.get('humidity_percent')} battery={row.get('battery_percent')} "
        f"voltage={row.get('voltage_mv')} lqi={row.get('linkquality')} available={row.get('available')}"
    )

for ieee in ("0xa4c13810e66fffff","0xa4c13810bdedffff"):
    row=rows[ieee]
    if row.get("temperature_celsius") is None or row.get("battery_percent") is None:
        raise SystemExit(f"ERROR: retained system sensor telemetry missing after core restart: {row!r}")
print("retained NAWIEW/WYWIEW telemetry in common list: PASS")
print("temp_zew common-list row: PASS")
PY

section "ROLE REGISTRY MIGRATION"
python3 - <<'PY'
import json
from pathlib import Path
path=Path("/var/lib/workshop-ventilation/zigbee-roles.json")
p=json.loads(path.read_text())
if p.get("version") != 2:
    raise SystemExit(f"ERROR: expected role registry version 2, got {p.get('version')!r}")
if not isinstance(p.get("other"),list):
    raise SystemExit("ERROR: role registry 'other' is not a list")
roles=p.get("roles") or {}
for role in ("supply","extract"):
    if not isinstance(roles.get(role),dict):
        raise SystemExit(f"ERROR: existing system role lost during migration: {role}")
print("role registry v2 migration: PASS")
print("multi-device OTHER registry ready: PASS")
PY

section "RESTART WEB AND WAIT FOR LISTENER"
systemctl restart wvc-web-ui.service
WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"
fetch_url(){
    python3 - "$1" "$2" <<'PY'
import sys,urllib.request
url,target=sys.argv[1:3]
with urllib.request.urlopen(url,timeout=3.0) as r:
    if r.status != 200: raise SystemExit(1)
    open(target,"wb").write(r.read())
PY
}
web_ready=false
for _ in $(seq 1 80); do
    if fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}" 2>/dev/null; then web_ready=true; break; fi
    sleep 0.25
done
[[ "${web_ready}" == true ]] || fail "Web API did not become ready"
echo "web listener: PASS (${BASE_URL})"

section "WEB API IS CORE PROJECTION"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
z=p.get("zigbee") if p.get("ok") is True else None
if not isinstance(z,dict):
    raise SystemExit(f"ERROR: invalid Zigbee API: {p!r}")
rows={d.get("ieee_address"):d for d in z.get("sensor_list", [])}
for ieee in ("0xa4c13810e66fffff","0xa4c13810bdedffff","0xa4c13879a816c919"):
    if ieee not in rows:
        raise SystemExit(f"ERROR: Web API missing core sensor row {ieee}")
print("Web API projects core-owned common sensor list: PASS")
PY

section "GUI COMMON LIST CONTRACT"
fetch_url "${BASE_URL}/zigbee-settings.js" "${js_file}"
python3 - "${js_file}" <<'PY'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
for required in (
    "zigbee.sensor_list",
    "Temperatura",
    "Wilgotność",
    "Bateria",
    "Napięcie",
    "LQI",
    "Ostatni pomiar",
    'option value="other"',
    "INNE",
    "Rola systemowa",
):
    if required not in s:
        raise SystemExit(f"ERROR: missing Stage 14 GUI contract: {required}")
for forbidden in ("zigbeeDeviceGrid", "Czujniki temperatury kanałów", "window.confirm", "zigbee2mqtt/", "mosquitto"):
    if forbidden in s:
        raise SystemExit(f"ERROR: forbidden Stage 14 GUI behavior/text found: {forbidden}")
print("single inventory list for all sensors: PASS")
print("actual readings rendered from core sensor_list: PASS")
print("OTHER role visible: PASS")
print("GUI remains client-only: PASS")
PY

section "NO MANAGEMENT MUTATION"
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["zigbee"]
expected={"0xa4c13810e66fffff","0xa4c13810bdedffff","0xa4c13879a816c919"}
actual={d.get("ieee_address") for d in z.get("inventory", [])}
if not expected.issubset(actual):
    raise SystemExit("ERROR: sensor inventory changed during Stage 14 validation")
if z.get("permit_join") is not False:
    raise SystemExit(f"ERROR: pairing unexpectedly open: {z.get('permit_join')!r}")
print("three known sensors remain paired: PASS")
print("permit_join remains false: PASS")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 14 PASS: all Zigbee sensors use one compact inventory list with core-owned readings."
echo "Validator did not open pairing, remove/rename devices or change any role assignment."
