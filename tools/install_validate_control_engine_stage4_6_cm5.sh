#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-control-engine-stage4-6-validation
BRANCH=agent/automation-v1-control-engine
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE46_EXPECTED_BRANCH_SHA:-}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-control-engine-stage4-6-validation.conf
TEST_ROOT=/var/tmp/wvc-control-engine-stage4-6-validation
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
ROLLOUT_STARTED=0
BOOT_ID_BEFORE=""
HOST_POWER_PID_BEFORE=""
HOST_POWER_STATUS_BEFORE=""
WAKEALARM_BEFORE=""

unit_pid() {
    systemctl show "$1" -p MainPID --value
}

unit_cwd() {
    local pid="$1"
    readlink -f "/proc/$pid/cwd"
}

ctl() {
    local src="$1"
    shift
    env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$src" /usr/bin/python3 -B -m ventilation_core.ctl "$@"
}

read_wakealarm() {
    sudo cat "$WAKEALARM" 2>/dev/null | tr -d '\r\n'
}

assert_host_not_touched() {
    local label="$1"
    local boot_id host_pid host_status wakealarm
    boot_id="$(cat /proc/sys/kernel/random/boot_id)"
    host_pid="$(unit_pid wvc-host-power.service)"
    host_status="$(systemctl show wvc-host-power.service -p StatusText --value)"
    wakealarm="$(read_wakealarm)"
    [ "$boot_id" = "$BOOT_ID_BEFORE" ] || { echo "FAIL: $label: boot_id changed" >&2; exit 1; }
    [ "$host_pid" = "$HOST_POWER_PID_BEFORE" ] || { echo "FAIL: $label: host-power PID changed" >&2; exit 1; }
    [ "$host_status" = "$HOST_POWER_STATUS_BEFORE" ] || { echo "FAIL: $label: host-power state changed" >&2; exit 1; }
    [ "$wakealarm" = "$WAKEALARM_BEFORE" ] || { echo "FAIL: $label: RTC wakealarm changed" >&2; exit 1; }
    echo "PASS: $label: same boot, same host-power process/state, unchanged RTC"
}

require_zero_output_guard() {
    local src="$1"
    local label="$2"
    local json
    json="$(ctl "$src" status)"
    /usr/bin/python3 - "$label" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
doc = json.loads(sys.argv[2])
if doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: status request failed: {doc!r}")
state = doc.get("state") or {}
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC setpoints are not 0 V: {sp!r}")
for channel in ("supply", "extract"):
    row = (state.get("tacho") or {}).get(channel)
    if isinstance(row, dict) and float(row.get("rpm") or 0.0) != 0.0:
        raise SystemExit(f"FAIL: {label}: {channel} TACHO reports motion: {row!r}")
print(f"PASS: {label}: EC=0 V and no observed local fan motion")
PY
}

assert_branch_runtime() {
    local label="$1"
    local pid cwd execstart
    pid="$(unit_pid "$CORE_UNIT")"
    [ -n "$pid" ] && [ "$pid" != "0" ] || { echo "FAIL: $label: core has no PID" >&2; exit 1; }
    cwd="$(unit_cwd "$pid")"
    [ "$cwd" = "$WT" ] || { echo "FAIL: $label: core CWD=$cwd, expected $WT" >&2; exit 1; }
    execstart="$(systemctl show "$CORE_UNIT" -p ExecStart --value)"
    case "$execstart" in
        *--enable-scheduled-shutdown*)
            echo "FAIL: $label: scheduled shutdown unexpectedly enabled" >&2
            exit 1
            ;;
    esac
    echo "PASS: $label: branch core active, scheduled shutdown disabled"
}

assert_shadow_zero_tacho() {
    local label="$1"
    local json
    json="$(ctl "$WT/src" status)"
    /usr/bin/python3 - "$label" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
state = (json.loads(sys.argv[2]).get("state") or {})
shadow = state.get("shadow_automation") or {}
if shadow.get("actuation_supported") is not False:
    raise SystemExit(f"FAIL: {label}: Control Engine gained actuation authority")
if shadow.get("configuration_persistent") is not True:
    raise SystemExit(f"FAIL: {label}: persistent Control Engine runtime unavailable")
zones = [row for row in shadow.get("zones") or [] if isinstance(row, dict)]
zone1 = next((row for row in zones if row.get("zone") == "zone-1"), None)
if not zone1:
    raise SystemExit(f"FAIL: {label}: zone-1 shadow telemetry missing")
for channel in ("supply", "extract"):
    if zone1.get(f"tacho_{channel}_feedback_required") is not False:
        raise SystemExit(f"FAIL: {label}: {channel} TACHO required at physical 0 V")
    if zone1.get(f"tacho_{channel}_status") != "NOT_REQUIRED":
        raise SystemExit(
            f"FAIL: {label}: {channel} TACHO status={zone1.get(f'tacho_{channel}_status')!r}, expected NOT_REQUIRED"
        )
    if zone1.get(f"tacho_{channel}_fault_confirmed") is not False:
        raise SystemExit(f"FAIL: {label}: {channel} TACHO fault confirmed at physical 0 V")
if zone1.get("proposed_supply_voltage") is not None or zone1.get("proposed_extract_voltage") is not None:
    raise SystemExit(f"FAIL: {label}: SHADOW exposed physical voltage proposal")
print(f"PASS: {label}: SHADOW-only and TACHO NOT_REQUIRED at actual 0 V")
PY
}

assert_operator_state() {
    local expected_mode="$1"
    local expected_revision="$2"
    local json
    json="$(ctl "$WT/src" control-engine-operator)"
    /usr/bin/python3 - "$expected_mode" "$expected_revision" "$json" <<'PY'
import json
import sys

expected_mode = sys.argv[1]
expected_revision = int(sys.argv[2])
doc = json.loads(sys.argv[3])
if doc.get("ok") is not True:
    raise SystemExit(f"FAIL: operator read failed: {doc!r}
")
operator = doc.get("operator") or {}
intent = operator.get("intent") or {}
if intent.get("mode") != expected_mode:
    raise SystemExit(f"FAIL: operator mode={intent.get('mode')!r}, expected {expected_mode!r}")
if operator.get("revision") != expected_revision:
    raise SystemExit(f"FAIL: operator revision={operator.get('revision')!r}, expected {expected_revision}")
if operator.get("persistent") is not False or operator.get("reset_on_core_restart") is not True:
    raise SystemExit(f"FAIL: operator persistence contract invalid: {operator!r}")
if operator.get("actuation_supported") is not False:
    raise SystemExit("FAIL: operator intent unexpectedly supports actuation")
print(f"PASS: operator {expected_mode}, revision={expected_revision}, volatile SHADOW-only")
PY
}

assert_shadow_operator_manual() {
    local json
    json="$(ctl "$WT/src" status)"
    /usr/bin/python3 - "$json" <<'PY'
import json
import sys

state = (json.loads(sys.argv[1]).get("state") or {})
shadow = state.get("shadow_automation") or {}
if shadow.get("operator_mode") != "MANUAL":
    raise SystemExit(f"FAIL: shadow operator_mode={shadow.get('operator_mode')!r}")
if shadow.get("operator_manual_supply_pct") != 37.0:
    raise SystemExit("FAIL: shadow manual supply telemetry mismatch")
if shadow.get("operator_manual_extract_pct") != 43.0:
    raise SystemExit("FAIL: shadow manual extract telemetry mismatch")
if shadow.get("operator_manual_aero_speed") != 2:
    raise SystemExit("FAIL: shadow manual AERO telemetry mismatch")
if shadow.get("actuation_supported") is not False:
    raise SystemExit("FAIL: MANUAL shadow unexpectedly supports actuation")
for zone in shadow.get("zones") or []:
    if not isinstance(zone, dict):
        continue
    if zone.get("operator_mode") != "MANUAL":
        raise SystemExit(f"FAIL: zone {zone.get('zone')!r} did not receive MANUAL intent")
    if zone.get("proposed_supply_voltage") is not None or zone.get("proposed_extract_voltage") is not None:
        raise SystemExit("FAIL: MANUAL shadow exposed physical voltage proposal")
print("PASS: MANUAL intent visible in authoritative SHADOW telemetry")
PY
}

restore_production() {
    local rc="$1"
    set +e
    sudo rm -f "$CORE_DROPIN"
    sudo systemctl daemon-reload
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        sudo systemctl restart "$CORE_UNIT"
        sleep 3
    fi
    if [ -d "$WT" ]; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    fi
    rm -rf "$TEST_ROOT"
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        local pid cwd
        pid="$(unit_pid "$CORE_UNIT")"
        cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
        if [ "$cwd" != "$ROOT" ]; then
            echo "CRITICAL: rollback core CWD=$cwd, expected $ROOT" >&2
            rc=1
        fi
    fi
    exit "$rc"
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    restore_production "$rc"
}
trap emergency_rollback EXIT INT TERM

if [ -z "$EXPECTED_BRANCH_SHA" ]; then
    echo "FAIL: set CONTROL_ENGINE_STAGE46_EXPECTED_BRANCH_SHA to the exact CI-tested branch SHA" >&2
    exit 2
fi

cd "$ROOT"
echo "===== CONTROL ENGINE STAGE4-6 CM5 NON-ACTUATING VALIDATION ====="

echo "===== 1. FETCH AND PIN ====="
git fetch origin main "$BRANCH"
MAIN_REMOTE="$(git rev-parse origin/main)"
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
[ "$MAIN_REMOTE" = "$EXPECTED_BASE" ] || { echo "FAIL: origin/main moved: $MAIN_REMOTE" >&2; exit 1; }
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || { echo "FAIL: branch SHA=$BRANCH_SHA expected=$EXPECTED_BRANCH_SHA" >&2; exit 1; }
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || { echo "FAIL: local production checkout is not expected main" >&2; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: production checkout is dirty" >&2; exit 1; }
MAIN_PID="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID")" = "$ROOT" ] || { echo "FAIL: production core does not run from main" >&2; exit 1; }

BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"
HOST_POWER_STATUS_BEFORE="$(systemctl show wvc-host-power.service -p StatusText --value)"
WAKEALARM_BEFORE="$(read_wakealarm)"

require_zero_output_guard "$ROOT/src" "production preflight"
assert_host_not_touched "production preflight"

echo "===== 2. ISOLATED WORKTREE ====="
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
if [ -d "$WT" ]; then
    git worktree remove --force "$WT"
fi
git worktree add --detach "$WT" "$BRANCH_SHA"
[ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ] || { echo "FAIL: worktree SHA mismatch" >&2; exit 1; }

cat >"$TEST_ROOT/manual.json" <<'JSON'
{
  "mode": "MANUAL",
  "manual_supply_pct": 37.0,
  "manual_extract_pct": 43.0,
  "manual_aero_speed": 2
}
JSON
cat >"$TEST_ROOT/auto.json" <<'JSON'
{
  "mode": "AUTO"
}
JSON

sudo mkdir -p "$CORE_DROPIN_DIR"
sudo tee "$CORE_DROPIN" >/dev/null <<EOF
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
EOF
sudo systemctl daemon-reload
ROLLOUT_STARTED=1
sudo systemctl restart "$CORE_UNIT"
sleep 3

assert_branch_runtime "branch startup"
require_zero_output_guard "$WT/src" "branch startup"
assert_shadow_zero_tacho "branch startup"
assert_operator_state AUTO 0
assert_host_not_touched "branch startup"

echo "===== 3. VOLATILE MANUAL INTENT ====="
ctl "$WT/src" control-engine-operator-replace --file "$TEST_ROOT/manual.json" >/dev/null
assert_operator_state MANUAL 1
assert_shadow_operator_manual
require_zero_output_guard "$WT/src" "after MANUAL shadow intent"
assert_shadow_zero_tacho "after MANUAL shadow intent"
assert_host_not_touched "after MANUAL shadow intent"

echo "===== 4. RETURN TO AUTO ====="
ctl "$WT/src" control-engine-operator-replace --file "$TEST_ROOT/auto.json" >/dev/null
assert_operator_state AUTO 2
require_zero_output_guard "$WT/src" "after AUTO restore"
assert_shadow_zero_tacho "after AUTO restore"
assert_host_not_touched "after AUTO restore"

echo "===== 5. CORE RESTART MUST RESET OPERATOR INTENT ====="
sudo systemctl restart "$CORE_UNIT"
sleep 3
assert_branch_runtime "branch restart"
assert_operator_state AUTO 0
require_zero_output_guard "$WT/src" "after branch restart"
assert_shadow_zero_tacho "after branch restart"
assert_host_not_touched "after branch restart"

echo "===== 6. RESULT ====="
echo "PASS: Stage4-6 CM5 non-actuating validation"
echo "PASS: MANUAL was volatile and visible only in SHADOW"
echo "PASS: actual EC outputs stayed at 0 V and no local fan motion was observed"
echo "PASS: TACHO remained NOT_REQUIRED at actual 0 V"
echo "PASS: core restart reset operator intent to AUTO revision 0"
echo "PASS: host-power process/state, RTC wakealarm and boot id were unchanged"

trap - EXIT INT TERM
restore_production 0
