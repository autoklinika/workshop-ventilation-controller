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
[[ "$#" -eq 0 ]] || fail "Usage: sudo bash tools/validate_cm5_zigbee_pairing_capabilities_stage13.sh [--allow-hardware-offline]"
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
css_file="$(mktemp)"
trap 'rm -f "${state_file:-}" "${api_file:-}" "${js_file:-}" "${css_file:-}"' EXIT

section "SAFE STATE PRECHECK"
PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}"
python3 - "${state_file}" "${ALLOW_HARDWARE_OFFLINE}" <<'PY'
import json,sys
from pathlib import Path
state=json.loads(Path(sys.argv[1]).read_text())["state"]
offline=sys.argv[2].lower()=="true"
sp=state["setpoints"]
supply=float(sp["supply_voltage"])
extract=float(sp["extract_voltage"])
if supply != 0.0 or extract != 0.0:
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
    tests.test_zigbee_pairing_capabilities_stage13 \
    tests.test_zigbee_core_confirmation_stage12 \
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
by_ieee={d.get("ieee_address"):d for d in z.get("inventory", [])}
expected={"0xa4c13810e66fffff","0xa4c13810bdedffff"}
ok=(
    z.get("connected") is True
    and z.get("bridge_online") is True
    and expected.issubset(by_ieee)
)
raise SystemExit(0 if ok else 1)
PY
        then ready=true; break; fi
    fi
    sleep 0.25
done
[[ "${ready}" == true ]] || fail "ventilation-core did not restore Zigbee inventory in time"
echo "ventilation-core Zigbee inventory: ready"

section "CORE CAPABILITY INVENTORY"
python3 - "${state_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["state"]["zigbee"]
by_ieee={d.get("ieee_address"):d for d in z.get("inventory", [])}
expected={
    "0xa4c13810e66fffff":"czujnik 1",
    "0xa4c13810bdedffff":"czujnik 2",
}
for ieee,label in expected.items():
    device=by_ieee.get(ieee)
    if device is None:
        raise SystemExit(f"ERROR: missing {label} {ieee}")
    props={c.get("property") for c in device.get("capabilities", [])}
    missing={"temperature","battery"}-props
    if missing:
        raise SystemExit(
            f"ERROR: {device.get('friendly_name')} has no required published capabilities {sorted(missing)}; "
            f"available={sorted(p for p in props if p)}"
        )
    print(f"{device.get('friendly_name')} {ieee}: model={device.get('model')} capabilities={sorted(p for p in props if p)} PASS")

# Retained bridge/devices after a core restart must populate inventory only. It
# must not impersonate a fresh pairing event and open a false 'new device' modal.
if z.get("pairing") is not None:
    raise SystemExit(f"ERROR: false pairing state restored from retained inventory: {z.get('pairing')!r}")
print("retained inventory does not create false new-pairing state: PASS")
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
if p.get("ok") is not True or not isinstance(p.get("zigbee"),dict):
    raise SystemExit(f"ERROR: invalid Zigbee Web API: {p!r}")
z=p["zigbee"]
by_ieee={d.get("ieee_address"):d for d in z.get("inventory", [])}
for ieee in ("0xa4c13810e66fffff","0xa4c13810bdedffff"):
    props={c.get("property") for c in (by_ieee.get(ieee) or {}).get("capabilities", [])}
    if not {"temperature","battery"}.issubset(props):
        raise SystemExit(f"ERROR: Web API does not project core capabilities for {ieee}: {props!r}")
print("Web API projects core-owned capabilities: PASS")
PY

section "GUI CLIENT-ONLY CONTRACT"
fetch_url "${BASE_URL}/zigbee-settings.js" "${js_file}"
fetch_url "${BASE_URL}/zigbee-stage13.css" "${css_file}"
python3 - "${js_file}" <<'PY'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
for required in (
    "CM5 · VENTILATION-CORE",
    "URZĄDZENIE ZIGBEE ROZPOZNANE",
    "DOSTĘPNE DANE",
    "/api/v1/zigbee/pairing/ack",
    "currentPairing.capabilities",
    "currentRemovalConfirmation.last_error",
):
    if required not in s:
        raise SystemExit(f"ERROR: missing Stage 13 GUI contract: {required}")
for forbidden in ("window.confirm", "zigbee2mqtt/", "mosquitto", "OSTATNIO ODEBRANE", "ostatnio odebrane"):
    if forbidden in s:
        raise SystemExit(f"ERROR: forbidden browser-side Stage 13 behavior/text found: {forbidden}")
print("GUI renders pairing/capabilities only from core state: PASS")
print("no browser MQTT/Zigbee2MQTT interpretation: PASS")
print("no 'ostatnio odebrane' section: PASS")
PY
[[ -s "${css_file}" ]] || fail "Stage 13 CSS was not served"
echo "Stage 13 pairing UI asset: PASS"

section "NO MANAGEMENT MUTATION"
fetch_url "${BASE_URL}/api/v1/zigbee" "${api_file}"
python3 - "${api_file}" <<'PY'
import json,sys
from pathlib import Path
z=json.loads(Path(sys.argv[1]).read_text())["zigbee"]
by_ieee={d.get("ieee_address") for d in z.get("inventory", [])}
expected={"0xa4c13810e66fffff","0xa4c13810bdedffff"}
if not expected.issubset(by_ieee):
    raise SystemExit("ERROR: sensor inventory changed during Stage 13 validation")
if z.get("permit_join") is not False:
    raise SystemExit(f"ERROR: pairing unexpectedly open: {z.get('permit_join')!r}")
print("both known sensors remain in inventory: PASS")
print("permit_join remains false: PASS")
PY

section "FINAL SERVICE CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 13 baseline PASS: capabilities are interpreted and owned by ventilation-core; GUI is client-only."
echo "Validator did not open pairing, remove/rename devices or change system roles."
echo "A real new-pairing modal can be checked later with one controlled re-pair if desired."
