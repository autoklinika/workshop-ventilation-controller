#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGINAL="${ROOT_DIR}/tools/validate_cm5_zigbee_stage11_roles.sh"
ALLOW_HARDWARE_OFFLINE=true

fail(){ echo "ERROR: $*" >&2; exit 1; }
section(){ printf '\n===== %s =====\n' "$1"; }

[[ "${EUID}" -eq 0 ]] || fail "Run with sudo"
[[ -f "${ORIGINAL}" ]] || fail "Missing validator: ${ORIGINAL}"

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
remainder="$(mktemp)"
trap 'rm -f "${state_file:-}" "${api_file:-}" "${js_file:-}" "${remainder:-}"' EXIT

section "SAFE STATE PRECHECK"
PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${state_file}" || fail "Unable to read ventilation-core state"
python3 - "${state_file}" <<'PY'
import json,sys
from pathlib import Path
state=json.loads(Path(sys.argv[1]).read_text())["state"]
sp=state["setpoints"]
supply=float(sp["supply_voltage"])
extract=float(sp["extract_voltage"])
mode=state.get("mode")
if supply != 0.0 or extract != 0.0:
    raise SystemExit(f"ERROR: standalone CM5 software outputs are not 0 V / 0 V: {sp!r}")
if mode not in {"STOP", "FAULT"}:
    raise SystemExit(f"ERROR: standalone CM5 expected safe STOP/FAULT, got {mode!r}")
print("standalone CM5 / execution hardware intentionally offline: PASS")
print(f"core mode: {mode}")
print("software setpoints: 0 V / 0 V")
print("hardware_ready:", state.get("hardware_ready"))
print("output_state_known:", state.get("output_state_known"))
PY

# The original Stage 11 run stopped before STATIC VALIDATION, so no Stage 11
# mutation was performed. Reuse the already-reviewed remainder of that validator
# instead of duplicating its test/deployment logic here.
sed -n '/^section "STATIC VALIDATION"/,$p' "${ORIGINAL}" >"${remainder}"
[[ -s "${remainder}" ]] || fail "Unable to locate Stage 11 validator remainder"

# shellcheck source=/dev/null
source "${remainder}"
