#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-control-engine-stage8a-readiness-validation
BRANCH=agent/automation-v1-control-engine
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE8A_EXPECTED_BRANCH_SHA:-}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-control-engine-stage8a-readiness-validation.conf
TEST_ROOT=/var/tmp/wvc-control-engine-stage8a-validation
PRODUCTION_AUTOMATION_DB=/var/lib/workshop-ventilation/automation.sqlite3
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
SUPPLY_NAME=temp_nawiew
SUPPLY_IEEE=0xa4c13810e66fffff
EXTRACT_NAME=temp_wywiew
EXTRACT_IEEE=0xa4c13810bdedffff
ROLLOUT_STARTED=0
BOOT_ID_BEFORE=""
HOST_POWER_PID_BEFORE=""
HOST_POWER_STATUS_BEFORE=""
WAKEALARM_BEFORE=""
PRODUCTION_CONTROL_ROW_BEFORE=""

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

read_production_control_row() {
    /usr/bin/python3 - "$PRODUCTION_AUTOMATION_DB" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
try:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
except sqlite3.OperationalError:
    print("__DB_UNAVAILABLE__")
    raise SystemExit(0)
try:
    try:
        row = connection.execute(
            "SELECT revision, schema_version, config_json FROM control_engine_configuration WHERE singleton = 1"
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            print("__TABLE_ABSENT__")
            raise SystemExit(0)
        raise
    print("__ROW_ABSENT__" if row is None else repr(tuple(row)))
finally:
    connection.close()
PY
}

assert_host_untouched() {
    local label="$1"
    [ "$(cat /proc/sys/kernel/random/boot_id)" = "$BOOT_ID_BEFORE" ] || fail "$label: boot_id changed"
    [ "$(unit_pid wvc-host-power.service)" = "$HOST_POWER_PID_BEFORE" ] || fail "$label: host-power PID changed"
    [ "$(systemctl show wvc-host-power.service -p StatusText --value)" = "$HOST_POWER_STATUS_BEFORE" ] || fail "$label: host-power state changed"
    [ "$(read_wakealarm)" = "$WAKEALARM_BEFORE" ] || fail "$label: RTC wakealarm changed"
    echo "PASS: $label: same boot, same host-power process/state, unchanged RTC"
}

require_zero_output() {
    local src="$1"
    local label="$2"
    local json
    json="$(ctl "$src" status)"
    /usr/bin/python3 - "$label" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
state = (json.loads(sys.argv[2]).get("state") or {})
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
for channel in ("supply", "extract"):
    row = (state.get("tacho") or {}).get(channel) or {}
    if float(row.get("rpm") or 0.0) != 0.0:
        raise SystemExit(f"FAIL: {label}: {channel} reports fan motion: {row!r}")
shadow = state.get("shadow_automation") or {}
if shadow.get("actuation_supported") is not False:
    raise SystemExit(f"FAIL: {label}: Control Engine gained actuation authority")
print(f"PASS: {label}: EC=0 V / no observed motion / SHADOW non-actuating")
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
    case "$execstart" in
        *"--automation-db $TEST_ROOT/automation.sqlite3"*) ;;
        *) fail "$label: branch core is not using isolated automation DB" ;;
    esac
    echo "PASS: $label: exact branch runtime + isolated automation DB + scheduled shutdown disabled"
}

assert_readiness_blocked() {
    local src="$1"
    local label="$2"
    local json
    json="$(ctl "$src" status)"
    /usr/bin/python3 - "$label" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
state = (json.loads(sys.argv[2]).get("state") or {})
shadow = state.get("shadow_automation") or {}
readiness = shadow.get("actuation_readiness") or {}
blockers = set(readiness.get("blockers") or [])

if shadow.get("actuation_supported") is not False:
    raise SystemExit(f"FAIL: {label}: actuation_supported is not false")
if readiness.get("actuation_authorized") is not False:
    raise SystemExit(f"FAIL: {label}: readiness authority unexpectedly true")
if readiness.get("ready") is not False:
    raise SystemExit(f"FAIL: {label}: readiness unexpectedly true")
if readiness.get("preconditions_satisfied") is not False:
    raise SystemExit(f"FAIL: {label}: incomplete production tuning unexpectedly satisfies preconditions")

required = {
    "FAN_OUTPUT_TUNING_INCOMPLETE",
    "AERO_OUTPUT_TUNING_INCOMPLETE",
    "DYNAMICS_TUNING_INCOMPLETE",
    "FAN_SENSOR_FALLBACK_UNCONFIGURED",
    "AERO_SENSOR_FALLBACK_UNCONFIGURED",
    "TACHO_SUPPLY_FALLBACK_UNCONFIGURED",
    "TACHO_EXTRACT_FALLBACK_UNCONFIGURED",
    "TACHO_BOTH_FALLBACK_UNCONFIGURED",
    "ACTUATION_AUTHORITY_NOT_IMPLEMENTED",
}
missing = sorted(required - blockers)
if missing:
    raise SystemExit(f"FAIL: {label}: readiness blockers missing: {missing!r}; actual={sorted(blockers)!r}")
if "TACHO_CONFIRMATION_UNCONFIGURED" in blockers:
    raise SystemExit(f"FAIL: {label}: validated 4.0 s confirmation still reported unconfigured")

print(json.dumps({
    "preconditions_satisfied": readiness.get("preconditions_satisfied"),
    "actuation_authorized": readiness.get("actuation_authorized"),
    "ready": readiness.get("ready"),
    "blockers": sorted(blockers),
}, indent=2, sort_keys=True))
print(f"PASS: {label}: future-actuation readiness remains explicitly blocked")
PY
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

restore_production() {
    local rc="$1"
    set +e
    sudo rm -f "$CORE_DROPIN"
    sudo systemctl daemon-reload
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        sudo systemctl restart "$CORE_UNIT"
        sleep 6
    fi
    remove_worktree_best_effort
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        local pid cwd production_row_after
        pid="$(unit_pid "$CORE_UNIT")"
        cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
        if [ "$cwd" != "$ROOT" ]; then
            echo "CRITICAL: rollback core CWD=$cwd expected=$ROOT" >&2
            rc=1
        fi
        require_zero_output "$ROOT/src" "rollback production" || rc=1
        production_row_after="$(read_production_control_row)"
        if [ "$production_row_after" != "$PRODUCTION_CONTROL_ROW_BEFORE" ]; then
            echo "CRITICAL: production Control Engine SQLite row changed during isolated Stage8A" >&2
            rc=1
        else
            echo "PASS: production Control Engine SQLite row unchanged by isolated Stage8A"
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

[ -n "$EXPECTED_BRANCH_SHA" ] || fail "set CONTROL_ENGINE_STAGE8A_EXPECTED_BRANCH_SHA to exact CI-tested branch SHA"

cd "$ROOT"
echo "===== CONTROL ENGINE STAGE8A CM5 ACTUATION READINESS GATE VALIDATION ====="
echo "INFO: non-actuating test; local EC outputs must remain at 0 V"

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
PRODUCTION_CONTROL_ROW_BEFORE="$(read_production_control_row)"
require_zero_output "$ROOT/src" "production preflight"
assert_host_untouched "production preflight"

echo "===== 2. ISOLATED EXACT-SHA WORKTREE + TEST DB ====="
remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"
[ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ] || fail "worktree SHA mismatch"
if grep -q -- "--enable-scheduled-shutdown" "$WT/deploy/systemd/ventilation-core.service"; then
    fail "production unit unexpectedly enables scheduled shutdown"
fi

sudo mkdir -p "$CORE_DROPIN_DIR"
cat <<EOF | sudo tee "$CORE_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=
ExecStart=/usr/bin/python3 -B -m ventilation_core.main --socket /run/workshop-ventilation/ventilation-core.sock --alerts-db $TEST_ROOT/alerts.sqlite3 --alert-policy $WT/config/alerts-v2.default.toml --automation-db $TEST_ROOT/automation.sqlite3 --system-power-command /usr/bin/vcgencmd --system-power-timeout 0.5 --power-scheduler-poll-interval 1.0 --power-scheduler-minimum-wake-lead 120 --rtc-agent-socket /run/wvc-rtc/rtc-wake.sock --rtc-agent-timeout 2.0 --host-power-socket /run/wvc-host-power/host-power.sock --host-power-timeout 10.0 --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 --sensor-timeout 0.5 --sensor-poll-interval 1.0 --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 --aero-timeout 0.5 --aero-poll-interval 2.0 --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 --enable-supply-tacho --enable-extract-tacho --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 --tacho-timeout 0.25 --tacho-averaging-periods 6 --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt --zigbee-supply-name $SUPPLY_NAME --zigbee-supply-ieee $SUPPLY_IEEE --zigbee-extract-name $EXTRACT_NAME --zigbee-extract-ieee $EXTRACT_IEEE --zigbee-roles-file $TEST_ROOT/zigbee-roles.json --log-level INFO
EOF
sudo systemctl daemon-reload
ROLLOUT_STARTED=1
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_runtime "branch startup"
require_zero_output "$WT/src" "branch startup"
assert_host_untouched "branch startup"

echo "===== 3. APPLY PHYSICALLY VALIDATED 4.0s TO ISOLATED CONFIG ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 -B "$WT/tools/apply_validated_control_engine_tacho_confirmation.py" \
    --confirm-apply >/dev/null
sleep 1
require_zero_output "$WT/src" "after isolated 4.0 s config"
assert_readiness_blocked "$WT/src" "Stage8A readiness"
assert_host_untouched "Stage8A readiness"

echo "===== 4. RESTART AND VERIFY READINESS PERSISTS BLOCKED ====="
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_runtime "branch restart"
require_zero_output "$WT/src" "after branch restart"
assert_readiness_blocked "$WT/src" "Stage8A readiness after restart"
assert_host_untouched "Stage8A readiness after restart"

echo "===== 5. RESULT ====="
echo "PASS: Stage8A future-actuation readiness gate validation"
echo "PASS: physically validated 4.0 s removed only the TACHO confirmation blocker"
echo "PASS: output/dynamics/fallback prerequisites remain explicit blockers"
echo "PASS: actuation authority remains absent and readiness=false"
echo "PASS: local EC outputs remained at 0 V; host-power/RTC/boot untouched"
echo "PASS: production Control Engine SQLite row will be verified unchanged during rollback"

trap - EXIT INT TERM
restore_production 0
