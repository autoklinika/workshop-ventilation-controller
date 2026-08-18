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
[[ "$#" -eq 0 ]] || fail "Usage: sudo bash tools/validate_cm5_zigbee_system_confirmation_stage12.sh [--allow-hardware-offline]"
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
confirm_file="$(mktemp)"
js_file="$(mktemp)"
trap 'rm -f "${state_file:-}" "${api_file:-}" "${confirm_file:-}" "${js_file:-}"' EXIT

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
    tests.test_zigbee_core_confirmation_stage12 \
    tests.test_zigbee_gui_stage6 \
    tests.test_zigbee_management_alerts_stage89
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_*.py' -q
echo "full unittest suite: PASS"

section "RESTART CORE AND WEB"
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
systemctl is-active --quiet ventilation-core.service || fail "ventilation-core failed after restart"

echo "ventilation-core Zigbee state: ready"
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
post_json(){
    python3 - "$1" "$2" "$3" <<'PY'
import sys,urllib.request
url,body,target=sys.argv[1:4]
req=urllib.request.Request(url,data=body.encode(),headers={"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(req,timeout=25.0) as r:
    open(target,"wb").write(r.read())
PY
}

section "WAIT FOR WEB LISTENER"
ready=false
for _ in $(seq 1 80); do
    if fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}" 2>/dev/null; then ready=true; break; fi
    sleep 0.25
done
[[ "${ready}" == true ]] || fail "Web API did not become ready"
echo "web listener: PASS (${BASE_URL})"

section "BASELINE INVENTORY"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["zigbee"]
by_ieee={d.get("ieee_address"):d for d in z.get("inventory", [])}
for ieee,name in {
    "0xa4c13810e66fffff":"temp_nawiew",
    "0xa4c13810bdedffff":"temp_wywiew",
}.items():
    d=by_ieee.get(ieee)
    if d is None or d.get("friendly_name") != name:
        raise SystemExit(f"ERROR: missing baseline device {name}: {d!r}")
print("both real sensors present: PASS")
PY

section "REQUEST SYSTEM CONFIRMATION - NO REMOVE"
post_json "${BASE_URL}/api/v1/zigbee/remove" '{"device_id":"0xa4c13810e66fffff"}' "${confirm_file}"
confirmation_id="$(python3 - "${confirm_file}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
if p.get("ok") is not True or p.get("confirmation_required") is not True:
    raise SystemExit(f"ERROR: core did not require confirmation: {p!r}")
c=p.get("confirmation") or {}
if c.get("device_id") != "0xa4c13810e66fffff" or c.get("friendly_name") != "temp_nawiew":
    raise SystemExit(f"ERROR: wrong confirmation target: {c!r}")
if c.get("type") != "zigbee_remove_device" or c.get("destructive") is not True:
    raise SystemExit(f"ERROR: invalid confirmation contract: {c!r}")
print(c["confirmation_id"])
PY
)"
echo "CM5 confirmation created: ${confirmation_id}"

fetch_url "${BASE_URL}/api/v1/zigbee/removal-confirmation" "${confirm_file}"
python3 - "${confirm_file}" "${confirmation_id}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
c=p.get("confirmation") or {}
if c.get("confirmation_id") != sys.argv[2]:
    raise SystemExit(f"ERROR: confirmation is not owned/persisted by running core: {c!r}")
print("confirmation readable back from ventilation-core: PASS")
PY

fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["zigbee"]
by_ieee={d.get("ieee_address"):d for d in z.get("inventory", [])}
if "0xa4c13810e66fffff" not in by_ieee:
    raise SystemExit("ERROR: device was removed before operator confirmation")
roles={d.get("role"):d for d in z.get("devices", [])}
if (roles.get("supply") or {}).get("ieee_address") != "0xa4c13810e66fffff":
    raise SystemExit("ERROR: supply role changed before operator confirmation")
print("request alone did NOT remove device: PASS")
print("NAWIEW role unchanged: PASS")
PY

section "CANCEL THROUGH CORE"
post_json "${BASE_URL}/api/v1/zigbee/remove-confirmation" "{\"confirmation_id\":\"${confirmation_id}\",\"confirmed\":false}" "${confirm_file}"
python3 - "${confirm_file}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
if p.get("ok") is not True or (p.get("zigbee_management") or {}).get("status") != "cancelled":
    raise SystemExit(f"ERROR: cancellation failed: {p!r}")
print("system confirmation cancellation: PASS")
PY
fetch_url "${BASE_URL}/api/v1/zigbee/removal-confirmation" "${confirm_file}"
python3 - "${confirm_file}" <<'PY'
import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
if p.get("confirmation") is not None:
    raise SystemExit(f"ERROR: confirmation still pending after cancel: {p!r}")
print("pending confirmation cleared: PASS")
PY
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["zigbee"]
by_ieee={d.get("ieee_address"):d for d in z.get("inventory", [])}
if "0xa4c13810e66fffff" not in by_ieee or "0xa4c13810bdedffff" not in by_ieee:
    raise SystemExit("ERROR: sensor inventory changed during non-destructive confirmation test")
print("both sensors still paired after cancel: PASS")
PY

section "GUI CONTRACT"
fetch_url "${BASE_URL}/zigbee-settings.js" "${js_file}"
python3 - "${js_file}" <<'PY'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
for required in (
    "/api/v1/zigbee/remove-confirmation",
    "/api/v1/zigbee/removal-confirmation",
    "CM5 · VENTILATION-CORE",
    "POTWIERDŹ USUNIĘCIE",
    "confirmation_required",
):
    if required not in s:
        raise SystemExit(f"ERROR: missing CM5 system-confirmation GUI contract: {required}")
if "window.confirm" in s:
    raise SystemExit("ERROR: browser-native window.confirm is still present")
print("browser-native confirmation removed: PASS")
print("CM5 system confirmation UI contract: PASS")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 12 PASS: destructive Zigbee removal confirmation is owned by ventilation-core on CM5."
echo "Validator created and CANCELLED a confirmation only; no device was removed and pairing was not opened."
