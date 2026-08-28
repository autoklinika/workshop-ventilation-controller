#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-webgui-automation-stage2-runtime
BRANCH=agent/web-gui-automation-stage2-runtime
EXPECTED_MAIN=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${WEBGUI_AUTOMATION_STAGE2_EXPECTED_BRANCH_SHA:-}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-webgui-automation-stage2-runtime.conf
TEST_ROOT=/var/tmp/wvc-webgui-automation-stage2-runtime
STATE_FILE=${TEST_ROOT}/stage2-state.json
PRODUCTION_AUTOMATION_DB=/var/lib/workshop-ventilation/automation.sqlite3
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
WEB_PORT=18094
WEB_URL=http://127.0.0.1:${WEB_PORT}
WEB_PID=""
SUPPLY_NAME=temp_nawiew
SUPPLY_IEEE=0xa4c13810e66fffff
EXTRACT_NAME=temp_wywiew
EXTRACT_IEEE=0xa4c13810bdedffff
ROLLOUT_STARTED=0
BOOT_ID_BEFORE=""
HOST_POWER_PID_BEFORE=""
HOST_POWER_STATUS_BEFORE=""
WAKEALARM_BEFORE=""
PRODUCTION_AUTOMATION_ROWS_BEFORE=""

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

read_production_automation_rows() {
    /usr/bin/python3 - "$PRODUCTION_AUTOMATION_DB" <<'PY'
import json
import sqlite3
import sys

path = sys.argv[1]
result = {}
try:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
except sqlite3.OperationalError:
    print("__DB_UNAVAILABLE__")
    raise SystemExit(0)
try:
    for table in ("calendar_configuration", "control_engine_configuration"):
        try:
            row = connection.execute(
                f"SELECT revision, schema_version, config_json FROM {table} WHERE singleton = 1"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                result[table] = "__TABLE_ABSENT__"
                continue
            raise
        result[table] = "__ROW_ABSENT__" if row is None else list(row)
finally:
    connection.close()
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
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
    local require_shadow="${3:-0}"
    local json
    json="$(ctl "$src" status)"
    /usr/bin/python3 - "$label" "$require_shadow" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
require_shadow = sys.argv[2] == "1"
doc = json.loads(sys.argv[3])
if doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: core status rejected: {doc!r}")
state = doc.get("state") or {}
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
for channel in ("supply", "extract"):
    row = (state.get("tacho") or {}).get(channel) or {}
    if float(row.get("rpm") or 0.0) != 0.0:
        raise SystemExit(f"FAIL: {label}: {channel} TACHO reports motion: {row!r}")
aero = state.get("aero_bus") or {}
telemetry = aero.get("telemetry") if isinstance(aero, dict) else None
if isinstance(telemetry, dict):
    for key in ("fan_1_percent", "fan_2_percent"):
        value = telemetry.get(key)
        if value not in (None, 0):
            raise SystemExit(f"FAIL: {label}: AERO {key} reports motion: {telemetry!r}")
if require_shadow:
    shadow = state.get("shadow_automation") or {}
    if shadow.get("actuation_supported") is not False:
        raise SystemExit(f"FAIL: {label}: Control Engine gained actuation authority")
    readiness = shadow.get("actuation_readiness") or {}
    if readiness.get("actuation_authorized") is not False:
        raise SystemExit(f"FAIL: {label}: readiness authority unexpectedly true")
    if readiness.get("ready") is not False:
        raise SystemExit(f"FAIL: {label}: readiness unexpectedly true")
print(f"PASS: {label}: EC=0 V / no observed fan motion" + (" / SHADOW non-actuating" if require_shadow else ""))
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
    echo "PASS: $label: exact branch core + isolated automation DB + scheduled shutdown disabled"
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

stop_branch_web() {
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        kill "$WEB_PID" >/dev/null 2>&1 || true
        wait "$WEB_PID" 2>/dev/null || true
    fi
    WEB_PID=""
}

wait_branch_web_ready() {
    local attempt
    for attempt in $(seq 1 48); do
        if curl --silent --show-error --fail --max-time 2 "$WEB_URL/api/v1/state" >/dev/null 2>&1; then
            return 0
        fi
        if [ -n "$WEB_PID" ] && ! kill -0 "$WEB_PID" 2>/dev/null; then
            echo "FAIL: branch WebGUI exited unexpectedly" >&2
            [ -f "$TEST_ROOT/web.log" ] && tail -n 100 "$TEST_ROOT/web.log" >&2 || true
            return 1
        fi
        sleep 0.25
    done
    echo "FAIL: branch WebGUI did not become ready on $WEB_URL" >&2
    [ -f "$TEST_ROOT/web.log" ] && tail -n 100 "$TEST_ROOT/web.log" >&2 || true
    return 1
}

start_branch_web() {
    env \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONPATH="$WT/src" \
        PYTHONUNBUFFERED=1 \
        WVC_WEB_HOST=127.0.0.1 \
        WVC_WEB_PORT="$WEB_PORT" \
        WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock \
        WVC_WEB_TELEMETRY_DATABASE="$TEST_ROOT/telemetry.sqlite3" \
        WVC_WEB_ALERT_DATABASE="$TEST_ROOT/alerts.sqlite3" \
        WVC_WEB_WEATHER_SNAPSHOT="$TEST_ROOT/weather.json" \
        WVC_WEB_AI_ADVISORY_CACHE="$TEST_ROOT/ai-advisory.json" \
        /usr/bin/python3 -B -m ventilation_core.web.main \
        >"$TEST_ROOT/web.log" 2>&1 &
    WEB_PID=$!
    wait_branch_web_ready
    echo "PASS: branch WebGUI ready on $WEB_URL and connected to the real branch core socket (pid=$WEB_PID)"
}

write_core_dropin() {
    sudo install -d -m 0755 "$CORE_DROPIN_DIR"
    cat <<EOF | sudo tee "$CORE_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=
ExecStart=/usr/bin/python3 -B -m ventilation_core.main --socket /run/workshop-ventilation/ventilation-core.sock --alerts-db $TEST_ROOT/alerts.sqlite3 --alert-policy $WT/config/alerts-v2.default.toml --automation-db $TEST_ROOT/automation.sqlite3 --system-power-command /usr/bin/vcgencmd --system-power-timeout 0.5 --power-scheduler-poll-interval 1.0 --power-scheduler-minimum-wake-lead 120 --rtc-agent-socket /run/wvc-rtc/rtc-wake.sock --rtc-agent-timeout 2.0 --host-power-socket /run/wvc-host-power/host-power.sock --host-power-timeout 10.0 --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 --sensor-timeout 0.5 --sensor-poll-interval 1.0 --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 --aero-timeout 0.5 --aero-poll-interval 2.0 --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 --enable-supply-tacho --enable-extract-tacho --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 --tacho-timeout 0.25 --tacho-averaging-periods 6 --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt --zigbee-supply-name $SUPPLY_NAME --zigbee-supply-ieee $SUPPLY_IEEE --zigbee-extract-name $EXTRACT_NAME --zigbee-extract-ieee $EXTRACT_IEEE --zigbee-roles-file $TEST_ROOT/zigbee-roles.json --log-level INFO
EOF
    sudo chmod 0644 "$CORE_DROPIN"
}

restore_production() {
    local rc="$1"
    set +e
    stop_branch_web
    sudo rm -f "$CORE_DROPIN"
    sudo systemctl daemon-reload
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        sudo systemctl restart "$CORE_UNIT"
        sleep 6
    fi
    remove_worktree_best_effort

    if [ "$ROLLOUT_STARTED" = "1" ]; then
        local pid cwd production_rows_after
        pid="$(unit_pid "$CORE_UNIT")"
        cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
        if [ "$cwd" != "$ROOT" ]; then
            echo "CRITICAL: rollback core CWD=$cwd expected=$ROOT" >&2
            rc=1
        fi
        require_zero_output "$ROOT/src" "rollback production main" 0 || rc=1
        production_rows_after="$(read_production_automation_rows)"
        if [ "$production_rows_after" != "$PRODUCTION_AUTOMATION_ROWS_BEFORE" ]; then
            echo "CRITICAL: production automation SQLite rows changed during isolated WebGUI Stage2" >&2
            echo "before: $PRODUCTION_AUTOMATION_ROWS_BEFORE" >&2
            echo "after:  $production_rows_after" >&2
            rc=1
        else
            echo "PASS: production Calendar/Control Engine SQLite rows unchanged by isolated Stage2"
        fi
        assert_host_untouched "rollback production main" || rc=1
        if [ "$(git -C "$ROOT" branch --show-current)" != "main" ] || \
           [ "$(git -C "$ROOT" rev-parse HEAD)" != "$EXPECTED_MAIN" ] || \
           [ -n "$(git -C "$ROOT" status --short)" ]; then
            echo "CRITICAL: production main checkout changed during Stage2" >&2
            rc=1
        else
            echo "PASS: production main remains clean at $EXPECTED_MAIN"
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

[ -n "$EXPECTED_BRANCH_SHA" ] || fail "set WEBGUI_AUTOMATION_STAGE2_EXPECTED_BRANCH_SHA to exact CI-tested branch SHA"

cd "$ROOT"
echo "===== WEBGUI AUTOMATION STAGE2 REAL CONTROL ENGINE CM5 VALIDATION ====="
echo "INFO: real branch ventilation-core + real hardware telemetry; Control Engine remains SHADOW-only"
echo "INFO: Calendar/Control Engine writes use only isolated $TEST_ROOT/automation.sqlite3"

echo "===== 1. PIN PRODUCTION AND BRANCH ====="
[ "$(git branch --show-current)" = "main" ] || fail "production checkout is not on main"
[ "$(git rev-parse HEAD)" = "$EXPECTED_MAIN" ] || fail "local main is not expected production SHA"
[ -z "$(git status --short)" ] || fail "production main working tree is dirty"
[ ! -e "$CORE_DROPIN" ] || fail "Stage2 core drop-in already exists: $CORE_DROPIN"

git fetch --no-tags origin main "$BRANCH"
MAIN_REMOTE="$(git rev-parse origin/main)"
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
MAIN_LS_REMOTE="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
BRANCH_LS_REMOTE="$(git ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
[ "$MAIN_REMOTE" = "$EXPECTED_MAIN" ] || fail "origin/main moved: $MAIN_REMOTE"
[ "$MAIN_LS_REMOTE" = "$EXPECTED_MAIN" ] || fail "remote main moved: $MAIN_LS_REMOTE"
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || fail "branch SHA=$BRANCH_SHA expected=$EXPECTED_BRANCH_SHA"
[ "$BRANCH_LS_REMOTE" = "$EXPECTED_BRANCH_SHA" ] || fail "remote branch SHA=$BRANCH_LS_REMOTE expected=$EXPECTED_BRANCH_SHA"

systemctl is-active --quiet "$CORE_UNIT" || fail "$CORE_UNIT is not active"
systemctl is-active --quiet wvc-host-power.service || fail "wvc-host-power.service is not active"
MAIN_PID_BEFORE="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID_BEFORE")" = "$ROOT" ] || fail "production core does not run from main"
BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"
HOST_POWER_STATUS_BEFORE="$(systemctl show wvc-host-power.service -p StatusText --value)"
WAKEALARM_BEFORE="$(read_wakealarm)"
PRODUCTION_AUTOMATION_ROWS_BEFORE="$(read_production_automation_rows)"
require_zero_output "$ROOT/src" "production preflight" 0
assert_host_untouched "production preflight"

echo "===== 2. ISOLATED EXACT-SHA BRANCH CORE ====="
remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"
[ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ] || fail "worktree SHA mismatch"
if grep -q -- "--enable-scheduled-shutdown" "$WT/deploy/systemd/ventilation-core.service"; then
    fail "production unit unexpectedly enables scheduled shutdown"
fi
[ -f "$WT/tools/apply_validated_control_engine_tacho_confirmation.py" ] || fail "validated TACHO patcher missing"
[ -f "$WT/tools/validate_web_gui_automation_stage2_runtime_cm5.py" ] || fail "Stage2 validator missing"

write_core_dropin
sudo systemctl daemon-reload
ROLLOUT_STARTED=1
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_runtime "branch startup"
require_zero_output "$WT/src" "branch startup" 1
assert_host_untouched "branch startup"

echo "===== 3. APPLY PHYSICALLY VALIDATED 4.0s TO ISOLATED CONTROL ENGINE ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 -B "$WT/tools/apply_validated_control_engine_tacho_confirmation.py" \
    --confirm-apply >/dev/null
sleep 1
require_zero_output "$WT/src" "after isolated 4.0 s config" 1
assert_host_untouched "after isolated 4.0 s config"

echo "===== 4. START WEBGUI AGAINST REAL BRANCH CORE ====="
start_branch_web

echo "===== 5. REAL RUNTIME ROUND-TRIP: STATE / HARMONOGRAM / MANUAL SHADOW ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 -B "$WT/tools/validate_web_gui_automation_stage2_runtime_cm5.py" \
    --phase prepare \
    --web-url "$WEB_URL" \
    --state-file "$STATE_FILE"
require_zero_output "$WT/src" "after WebGUI real-runtime prepare" 1
assert_host_untouched "after WebGUI real-runtime prepare"

echo "===== 6. RESTART REAL BRANCH CORE: CALENDAR PERSISTS / MANUAL DOES NOT ====="
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_runtime "branch restart"
require_zero_output "$WT/src" "after branch restart" 1
assert_host_untouched "after branch restart"
wait_branch_web_ready

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 -B "$WT/tools/validate_web_gui_automation_stage2_runtime_cm5.py" \
    --phase verify \
    --web-url "$WEB_URL" \
    --state-file "$STATE_FILE"
require_zero_output "$WT/src" "after WebGUI real-runtime verify" 1
assert_host_untouched "after WebGUI real-runtime verify"

echo "===== 7. RESULT ====="
echo "PASS: WebGUI Automation Stage2 integrated with the real CM5 Control Engine runtime"
echo "PASS: WebGUI read real state/SHADOW/TACHO/readiness through the real core socket"
echo "PASS: Harmonogram round-trip reached real Calendar Engine and persisted across restart in isolated SQLite"
echo "PASS: MANUAL reached real Control Engine SHADOW only; physical EC/AERO remained stopped"
echo "PASS: operator intent reset to volatile AUTO revision 0 after real core restart"
echo "PASS: validated TACHO confirmation 4.0 s remained visible through live SHADOW"
echo "PASS: actuation authority remained absent and readiness=false"
echo "PASS: production automation SQLite rows will be checked unchanged during rollback"
echo "branch SHA:       $BRANCH_SHA"
echo "production SHA:   $EXPECTED_MAIN"
echo "WebGUI test port: $WEB_PORT"

trap - EXIT INT TERM
restore_production 0
