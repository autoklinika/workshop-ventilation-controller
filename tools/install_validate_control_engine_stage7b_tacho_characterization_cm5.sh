#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-control-engine-stage7b-tacho-validation
BRANCH=agent/automation-v1-control-engine
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE7B_EXPECTED_BRANCH_SHA:-}"
CONFIRM_PHYSICAL_SPIN="${CONTROL_ENGINE_STAGE7B_CONFIRM_PHYSICAL_FAN_SPIN:-}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-control-engine-stage7b-tacho-validation.conf
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
ROLLOUT_STARTED=0
BOOT_ID_BEFORE=""
HOST_POWER_PID_BEFORE=""
HOST_POWER_STATUS_BEFORE=""
WAKEALARM_BEFORE=""

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

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

assert_host_untouched() {
    local label="$1"
    local boot_id host_pid host_status wakealarm
    boot_id="$(cat /proc/sys/kernel/random/boot_id)"
    host_pid="$(unit_pid wvc-host-power.service)"
    host_status="$(systemctl show wvc-host-power.service -p StatusText --value)"
    wakealarm="$(read_wakealarm)"
    [ "$boot_id" = "$BOOT_ID_BEFORE" ] || fail "$label: boot_id changed"
    [ "$host_pid" = "$HOST_POWER_PID_BEFORE" ] || fail "$label: host-power PID changed"
    [ "$host_status" = "$HOST_POWER_STATUS_BEFORE" ] || fail "$label: host-power state changed"
    [ "$wakealarm" = "$WAKEALARM_BEFORE" ] || fail "$label: RTC wakealarm changed"
    echo "PASS: $label: same boot, same host-power process/state, unchanged RTC"
}

require_safe_start() {
    local src="$1"
    local label="$2"
    local json
    json="$(ctl "$src" status)"
    /usr/bin/python3 - "$label" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
state = (json.loads(sys.argv[2]).get("state") or {})
if state.get("hardware_ready") is not True:
    raise SystemExit(f"FAIL: {label}: hardware_ready is not true")
if state.get("output_state_known") is not True:
    raise SystemExit(f"FAIL: {label}: output_state_known is not true")
if state.get("mode") != "STOP":
    raise SystemExit(f"FAIL: {label}: mode is not STOP")
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
tacho = state.get("tacho") or {}
if tacho.get("ready") is not True or tacho.get("worker_alive") is not True:
    raise SystemExit(f"FAIL: {label}: TACHO monitor not ready/alive")
for channel in ("supply", "extract"):
    row = tacho.get(channel)
    if not isinstance(row, dict):
        raise SystemExit(f"FAIL: {label}: TACHO channel {channel} missing")
    if float(row.get("rpm") or 0.0) != 0.0:
        raise SystemExit(f"FAIL: {label}: {channel} still reports motion: {row!r}")
shadow = state.get("shadow_automation") or {}
if shadow.get("actuation_supported") is not False:
    raise SystemExit(f"FAIL: {label}: Control Engine gained actuation authority")
print(f"PASS: {label}: STOP / 0 V / no observed motion / TACHO ready / SHADOW non-actuating")
PY
}

assert_branch_runtime() {
    local label="$1"
    local pid cwd execstart
    pid="$(unit_pid "$CORE_UNIT")"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "$label: invalid core PID"
    cwd="$(unit_cwd "$pid")"
    [ "$cwd" = "$WT" ] || fail "$label: core CWD=$cwd expected=$WT"
    execstart="$(systemctl show "$CORE_UNIT" -p ExecStart --value)"
    case "$execstart" in
        *--enable-scheduled-shutdown*) fail "$label: scheduled shutdown unexpectedly enabled" ;;
    esac
    echo "PASS: $label: exact branch runtime active, scheduled shutdown disabled"
}

best_effort_stop_current_core() {
    set +e
    if [ "$ROLLOUT_STARTED" = "1" ] && [ -S /run/workshop-ventilation/ventilation-core.sock ]; then
        ctl "$WT/src" stop >/dev/null 2>&1 || true
        sleep 1
    fi
}

restore_production() {
    local rc="$1"
    set +e
    best_effort_stop_current_core
    sudo rm -f "$CORE_DROPIN"
    sudo systemctl daemon-reload
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        sudo systemctl restart "$CORE_UNIT"
        sleep 3
    fi
    if [ -d "$WT" ]; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    fi
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        local pid cwd final_json
        pid="$(unit_pid "$CORE_UNIT")"
        cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
        if [ "$cwd" != "$ROOT" ]; then
            echo "CRITICAL: rollback core CWD=$cwd expected=$ROOT" >&2
            rc=1
        fi
        final_json="$(ctl "$ROOT/src" status 2>/dev/null || true)"
        /usr/bin/python3 - "$final_json" <<'PY'
import json
import sys
try:
    state = (json.loads(sys.argv[1]).get("state") or {})
except Exception:
    raise SystemExit(1)
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(1)
PY
        if [ $? -ne 0 ]; then
            echo "CRITICAL: rollback did not confirm production EC 0 V" >&2
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

[ "$CONFIRM_PHYSICAL_SPIN" = "YES" ] || fail "set CONTROL_ENGINE_STAGE7B_CONFIRM_PHYSICAL_FAN_SPIN=YES to acknowledge real fan motion"
[ -n "$EXPECTED_BRANCH_SHA" ] || fail "set CONTROL_ENGINE_STAGE7B_EXPECTED_BRANCH_SHA to exact CI-tested branch SHA"

cd "$ROOT"
echo "===== CONTROL ENGINE STAGE7B CM5 EXTENDED TACHO CHARACTERIZATION ====="
echo "WARNING: this test intentionally runs both local EC fans at 2.0 V for 15 s x 3 cycles, with STOP / 0 V between cycles"

echo "===== 1. PIN PRODUCTION AND BRANCH ====="
[ "$(git branch --show-current)" = "main" ] || fail "production checkout is not on main"
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || fail "local main is not expected production base"
[ -z "$(git status --short)" ] || fail "production checkout is dirty"

git fetch origin main "$BRANCH"
MAIN_REMOTE="$(git rev-parse origin/main)"
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
MAIN_LS_REMOTE="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
BRANCH_LS_REMOTE="$(git ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
[ "$MAIN_REMOTE" = "$EXPECTED_BASE" ] || fail "origin/main moved: $MAIN_REMOTE"
[ "$MAIN_LS_REMOTE" = "$EXPECTED_BASE" ] || fail "remote main moved: $MAIN_LS_REMOTE"
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || fail "branch SHA=$BRANCH_SHA expected=$EXPECTED_BRANCH_SHA"
[ "$BRANCH_LS_REMOTE" = "$EXPECTED_BRANCH_SHA" ] || fail "remote branch SHA=$BRANCH_LS_REMOTE expected=$EXPECTED_BRANCH_SHA"

systemctl is-active --quiet "$CORE_UNIT" || fail "$CORE_UNIT is not active"
systemctl is-active --quiet wvc-host-power.service || fail "wvc-host-power.service is not active"
MAIN_PID="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID")" = "$ROOT" ] || fail "production core does not run from main"

BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"
HOST_POWER_STATUS_BEFORE="$(systemctl show wvc-host-power.service -p StatusText --value)"
WAKEALARM_BEFORE="$(read_wakealarm)"

require_safe_start "$ROOT/src" "production preflight"
assert_host_untouched "production preflight"

echo "===== 2. ISOLATED EXACT-SHA WORKTREE ====="
if [ -d "$WT" ]; then
    git worktree remove --force "$WT"
fi
git worktree add --detach "$WT" "$BRANCH_SHA"
[ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ] || fail "worktree SHA mismatch"

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
require_safe_start "$WT/src" "branch startup"
assert_host_untouched "branch startup"

echo "===== 3. PHYSICAL 3-CYCLE EXTENDED TACHO CHARACTERIZATION ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT:$WT/src" \
    /usr/bin/python3 -B "$WT/tools/validate_control_engine_stage7b_tacho_characterization_cm5.py" \
    --confirm-fan-spin-test \
    --test-voltage 2.0 \
    --hold-seconds 15.0 \
    --cycles 3 \
    --poll 0.10 \
    --stop-timeout 10.0 \
    --rest-seconds 2.0 \
    --report-every 1.0 \
    --tail-window 5.0

require_safe_start "$WT/src" "after Stage7B characterization"
assert_host_untouched "after Stage7B characterization"

echo "===== 4. RESULT ====="
echo "PASS: Stage7B extended physical TACHO characterization completed"
echo "PASS: all three cycles used fixed 15 s hold at 2.0 V"
echo "PASS: physical fans returned to STOP / 0 V after every cycle"
echo "PASS: Control Engine remained SHADOW-only"
echo "PASS: no tuning value was written automatically"
echo "PASS: host-power, RTC and boot state were unchanged"

trap - EXIT INT TERM
restore_production 0
