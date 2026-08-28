#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-control-engine-stage7d-tacho-validation
BRANCH=agent/automation-v1-control-engine
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE7D_EXPECTED_BRANCH_SHA:-}"
CONFIRM_PHYSICAL_SPIN="${CONTROL_ENGINE_STAGE7D_CONFIRM_PHYSICAL_FAN_SPIN:-}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-control-engine-stage7d-tacho-validation.conf
TEST_ROOT=/var/tmp/wvc-control-engine-stage7d-validation
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
if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
    raise SystemExit(f"FAIL: {label}: hardware not ready/output state unknown")
if state.get("mode") != "STOP":
    raise SystemExit(f"FAIL: {label}: mode={state.get('mode')!r}, expected STOP")
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
tacho = state.get("tacho") or {}
if tacho.get("ready") is not True or tacho.get("worker_alive") is not True:
    raise SystemExit(f"FAIL: {label}: TACHO monitor not ready/alive")
for channel in ("supply", "extract"):
    row = tacho.get(channel) or {}
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
    case "$execstart" in
        *"--automation-db $TEST_ROOT/automation.sqlite3"*) ;;
        *) fail "$label: branch core is not using isolated automation DB" ;;
    esac
    echo "PASS: $label: exact branch runtime + isolated automation DB + scheduled shutdown disabled"
}

assert_tacho_config() {
    local expected_revision="$1"
    local src="$2"
    local json
    json="$(ctl "$src" control-engine)"
    /usr/bin/python3 - "$expected_revision" "$json" <<'PY'
import json
import sys

expected_revision = int(sys.argv[1])
doc = json.loads(sys.argv[2])
control = doc.get("control_engine") or {}
if control.get("actuation_supported") is not False:
    raise SystemExit("FAIL: Control Engine config unexpectedly supports actuation")
if control.get("revision") != expected_revision:
    raise SystemExit(
        f"FAIL: revision={control.get('revision')!r}, expected={expected_revision}"
    )
config = control.get("config") or {}
tuning = ((config.get("policy") or {}).get("tuning") or {})
if tuning.get("tacho_failure_confirmation_seconds") != 4.0:
    raise SystemExit(
        "FAIL: tacho_failure_confirmation_seconds is not persisted as 4.0"
    )
for name in (
    "tacho_supply_fault_fallback_supply_pct",
    "tacho_supply_fault_fallback_extract_pct",
    "tacho_extract_fault_fallback_supply_pct",
    "tacho_extract_fault_fallback_extract_pct",
    "tacho_both_fault_fallback_supply_pct",
    "tacho_both_fault_fallback_extract_pct",
):
    if tuning.get(name) is not None:
        raise SystemExit(f"FAIL: Stage7D must not configure fallback field {name}")
print(
    f"PASS: isolated Control Engine revision={expected_revision}; "
    "TACHO confirmation=4.0s; all TACHO fallbacks remain null"
)
PY
}

best_effort_stop_current_core() {
    set +e
    if [ "$ROLLOUT_STARTED" = "1" ] && [ -S /run/workshop-ventilation/ventilation-core.sock ]; then
        ctl "$WT/src" stop >/dev/null 2>&1 || true
        sleep 1
    fi
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
    best_effort_stop_current_core
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
        if ! require_safe_start "$ROOT/src" "rollback production"; then
            rc=1
        fi
        production_row_after="$(read_production_control_row)"
        if [ "$production_row_after" != "$PRODUCTION_CONTROL_ROW_BEFORE" ]; then
            echo "CRITICAL: production control_engine_configuration row changed during isolated Stage7D" >&2
            echo "before: $PRODUCTION_CONTROL_ROW_BEFORE" >&2
            echo "after:  $production_row_after" >&2
            rc=1
        else
            echo "PASS: production Control Engine SQLite row unchanged by isolated Stage7D"
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

[ "$CONFIRM_PHYSICAL_SPIN" = "YES" ] || fail "set CONTROL_ENGINE_STAGE7D_CONFIRM_PHYSICAL_FAN_SPIN=YES to acknowledge real fan motion"
[ -n "$EXPECTED_BRANCH_SHA" ] || fail "set CONTROL_ENGINE_STAGE7D_EXPECTED_BRANCH_SHA to exact CI-tested branch SHA"

cd "$ROOT"
echo "===== CONTROL ENGINE STAGE7D CM5 4.0s TACHO CONFIRMATION VALIDATION ====="
echo "WARNING: this test intentionally commands both local EC fans to 1.0 V, using an isolated automation DB"

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
require_safe_start "$ROOT/src" "production preflight"
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
require_safe_start "$WT/src" "branch startup"
assert_host_untouched "branch startup"

echo "===== 3. APPLY VALIDATED 4.0s TO ISOLATED CONFIG ====="
INITIAL_JSON="$(ctl "$WT/src" control-engine)"
/usr/bin/python3 - "$INITIAL_JSON" <<'PY'
import json
import sys
control = (json.loads(sys.argv[1]).get("control_engine") or {})
tuning = (((control.get("config") or {}).get("policy") or {}).get("tuning") or {})
if control.get("revision") != 1:
    raise SystemExit(f"FAIL: expected isolated initial revision 1, got {control.get('revision')!r}")
if tuning.get("tacho_failure_confirmation_seconds") is not None:
    raise SystemExit("FAIL: isolated initial TACHO confirmation is not null")
print("PASS: isolated config starts at revision=1 with TACHO confirmation null")
PY

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 -B "$WT/tools/apply_validated_control_engine_tacho_confirmation.py" \
    --confirm-apply
assert_tacho_config 2 "$WT/src"

echo "===== 4. RESTART BRANCH CORE AND VERIFY PERSISTENCE ====="
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_runtime "branch restart"
assert_tacho_config 2 "$WT/src"
require_safe_start "$WT/src" "after branch restart"
assert_host_untouched "after branch restart"

echo "===== 5. PHYSICAL 1.0 V CONFIRMING -> HEALTHY VALIDATION ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT:$WT/src" \
    /usr/bin/python3 -B "$WT/tools/validate_control_engine_stage7d_tacho_confirmation_cm5.py" \
    --confirm-fan-spin-test \
    --test-voltage 1.0 \
    --confirmation-seconds 4.0 \
    --timeout 8.0 \
    --stable-seconds 2.0 \
    --poll 0.10 \
    --stop-timeout 10.0

require_safe_start "$WT/src" "after Stage7D physical validation"
assert_tacho_config 2 "$WT/src"
assert_host_untouched "after Stage7D physical validation"

echo "===== 6. RESULT ====="
echo "PASS: Stage7D isolated persistent 4.0s TACHO confirmation validation completed"
echo "PASS: physical 1.0 V start reached HEALTHY without false confirmed TACHO fault"
echo "PASS: all TACHO fallback values remained null"
echo "PASS: physical fans returned to STOP / 0 V"
echo "PASS: Control Engine remained SHADOW-only"
echo "PASS: production Control Engine SQLite row will be checked unchanged during rollback"
echo "PASS: host-power, RTC and boot state were unchanged"

trap - EXIT INT TERM
restore_production 0
