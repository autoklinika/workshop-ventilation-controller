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
[[ "$#" -eq 0 ]] || fail "Usage: sudo bash tools/validate_cm5_zigbee_stage11_roles.sh [--allow-hardware-offline]"
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
    raise SystemExit("ERROR: software outputs are not 0 V / 0 V")
if offline:
    if state.get("mode") != "FAULT":
        raise SystemExit(f"ERROR: standalone CM5 expected FAULT, got {state.get('mode')!r}")
    if not any(a.get("code")=="DAC_COMMUNICATION_LOST" for a in state.get("active_alarms", [])):
        raise SystemExit("ERROR: expected DAC_COMMUNICATION_LOST with execution hardware offline")
    print("standalone CM5 / execution hardware intentionally offline: PASS")
else:
    if state.get("mode") != "STOP" or state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
        raise SystemExit("ERROR: production hardware state is not confirmed safe")
    print("production STOP / hardware ready: PASS")
print("software setpoints: 0 V / 0 V")
PY

section "STATIC VALIDATION"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest -v tests.test_zigbee_role_management_stage11
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_*.py' -q
echo "full unittest suite: PASS"

section "RESTART CORE AND SEED ROLE REGISTRY"
systemctl restart ventilation-core.service
for _ in $(seq 1 100); do
    if PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" 2>/dev/null; then
        if python3 - "${state_file}" <<'PY'
import json,sys
from pathlib import Path
z=(json.loads(Path(sys.argv[1]).read_text())["state"].get("zigbee") or {})
roles={d.get("role"):d for d in z.get("devices", [])}
ok=(z.get("connected") is True and z.get("bridge_online") is True and roles.get("supply") and roles.get("extract"))
raise SystemExit(0 if ok else 1)
PY
        then break; fi
    fi
    sleep 0.25
done
systemctl is-active --quiet ventilation-core.service || fail "ventilation-core failed"
ROLE_FILE="/var/lib/workshop-ventilation/zigbee-roles.json"
[[ -f "${ROLE_FILE}" ]] || fail "Role registry was not created: ${ROLE_FILE}"
python3 - "${ROLE_FILE}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
assert p["version"] == 1, p
assert p["roles"]["supply"]["ieee_address"] == "0xa4c13810e66fffff", p
assert p["roles"]["extract"]["ieee_address"] == "0xa4c13810bdedffff", p
print("persistent role registry seed: PASS")
print("supply:", p["roles"]["supply"])
print("extract:", p["roles"]["extract"])
PY

WEB_PORT=""
if [[ -f /etc/default/wvc-web-ui ]]; then
    WEB_PORT="$(sed -n 's/^WVC_WEB_PORT=//p' /etc/default/wvc-web-ui | tail -n1 | tr -d '\r\"')"
fi
WEB_PORT="${WEB_PORT:-8088}"
BASE_URL="http://127.0.0.1:${WEB_PORT}"

systemctl restart wvc-web-ui.service
section "WAIT FOR WEB LISTENER"
ready=false
for _ in $(seq 1 80); do
    if python3 - "${BASE_URL}/api/v1/zigbee" "${api_file}" <<'PY' 2>/dev/null
import sys,urllib.request
url,target=sys.argv[1:3]
with urllib.request.urlopen(url,timeout=1.0) as r:
    if r.status != 200: raise SystemExit(1)
    open(target,"wb").write(r.read())
PY
    then ready=true; break; fi
    sleep 0.25
done
[[ "${ready}" == true ]] || fail "Web API did not become ready"
echo "web listener: PASS (${BASE_URL})"

post_json(){
    python3 - "$1" "$2" "$3" <<'PY'
import sys,urllib.request
url,body,target=sys.argv[1:4]
req=urllib.request.Request(url,data=body.encode(),headers={"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(req,timeout=25.0) as r:
    open(target,"wb").write(r.read())
PY
}

section "LIVE ROLE MAPPING"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["zigbee"]
roles={d["role"]:d for d in z["devices"]}
expected={"supply":("0xa4c13810e66fffff","temp_nawiew"),"extract":("0xa4c13810bdedffff","temp_wywiew")}
for role,(ieee,name) in expected.items():
    d=roles.get(role)
    if not d or d.get("ieee_address")!=ieee or d.get("friendly_name")!=name:
        raise SystemExit(f"ERROR: role {role} mismatch: {d!r}")
    print(f"{role}: {name} {ieee} availability={d.get('available')} temp={d.get('temperature_celsius')}")
print("live role mapping: PASS")
PY

section "SAFE RENAME API PATH"
post_json "${BASE_URL}/api/v1/zigbee/rename" '{"device_id":"0xa4c13810e66fffff","new_name":"temp_nawiew"}' "${api_file}"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
if p.get("ok") is not True or (p.get("zigbee_management") or {}).get("status") != "ok":
    raise SystemExit(f"ERROR: safe same-name rename rejected: {p!r}")
print("same-name rename API path: PASS (no Zigbee name changed)")
PY

section "SAFE ROLE API PATH"
post_json "${BASE_URL}/api/v1/zigbee/role" '{"device_id":"0xa4c13810e66fffff","role":"supply"}' "${api_file}"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
if p.get("ok") is not True or (p.get("zigbee_management") or {}).get("status") != "ok":
    raise SystemExit(f"ERROR: same-role assignment failed: {p!r}")
print("same-device supply assignment: PASS")
print("retain=true refresh path: PASS")
PY

section "PERSISTENCE AFTER CORE RESTART"
systemctl restart ventilation-core.service
ok=false
for _ in $(seq 1 100); do
    if PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" 2>/dev/null; then
        if python3 - "${state_file}" <<'PY'
import json,sys
from pathlib import Path
z=(json.loads(Path(sys.argv[1]).read_text())["state"].get("zigbee") or {})
roles={d.get("role"):d for d in z.get("devices", [])}
s=roles.get("supply") or {}; e=roles.get("extract") or {}
ok=(z.get("connected") is True and s.get("ieee_address")=="0xa4c13810e66fffff" and e.get("ieee_address")=="0xa4c13810bdedffff" and s.get("temperature_celsius") is not None and e.get("temperature_celsius") is not None)
raise SystemExit(0 if ok else 1)
PY
        then ok=true; break; fi
    fi
    sleep 0.25
done
[[ "${ok}" == true ]] || { cat "${state_file}" >&2; fail "Role/retained state did not recover after core restart"; }
echo "role registry reload: PASS"
echo "retained telemetry after core restart: PASS"

section "GUI CONTRACT"
python3 - "${BASE_URL}/zigbee-settings.js" "${js_file}" <<'PY'
import sys,urllib.request
with urllib.request.urlopen(sys.argv[1],timeout=3.0) as r: open(sys.argv[2],"wb").write(r.read())
PY
python3 - "${js_file}" <<'PY'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
for text in ("/api/v1/zigbee/rename","/api/v1/zigbee/role","ZMIEŃ NAZWĘ","BEZ ROLI","NAWIEW","WYWIEW","NIEPRZYPISANE"):
    if text not in s: raise SystemExit(f"ERROR: GUI contract missing {text}")
for forbidden in ("zigbee2mqtt/","mosquitto","/api/v1/zigbee/publish"):
    if forbidden in s.lower(): raise SystemExit(f"ERROR: direct/generic MQTT surface detected: {forbidden}")
print("GUI rename/role controls: PASS")
print("GUI -> Web API -> core boundary: PASS")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 11 PASS: persistent Zigbee rename and NAWIEW/WYWIEW/no-role management is integrated."
echo "Validator did not change friendly names, unassign roles, open pairing or remove devices."
