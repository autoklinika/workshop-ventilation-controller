#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-calendar-m3-validation
BRANCH=agent/automation-v1-scheduler-assumptions
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
UNIT=ventilation-core.service
DROPIN_DIR=/etc/systemd/system/${UNIT}.d
DROPIN_PATH=${DROPIN_DIR}/99-zz-calendar-m3-validation.conf
TEST_ROOT=/var/tmp/wvc-calendar-m3-validation
STATE_FILE=${TEST_ROOT}/validation-state.json
WEB_PORT=18092
WEB_URL=http://127.0.0.1:${WEB_PORT}
WEB_PID=""
BRANCH_SHA=""

unit_pid() {
    systemctl show "$UNIT" -p MainPID --value
}

unit_cwd() {
    local pid="$1"
    readlink -f "/proc/$pid/cwd"
}

ctl() {
    local src="$1"
    shift
    env PYTHONPATH="$src" /usr/bin/python3 -m ventilation_core.ctl "$@"
}

require_safe_state() {
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
if state.get("mode") != "STOP":
    raise SystemExit(f"FAIL: {label}: mode is not STOP: {state.get('mode')!r}")
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
if state.get("output_state_known") is not True:
    raise SystemExit(f"FAIL: {label}: output_state_known is not true")

tacho = state.get("tacho")
if isinstance(tacho, dict):
    for channel in ("supply", "extract"):
        row = tacho.get(channel)
        if isinstance(row, dict) and float(row.get("rpm") or 0.0) != 0.0:
            raise SystemExit(f"FAIL: {label}: {channel} TACHO is not stopped: {row!r}")

aero = state.get("aero_bus")
if isinstance(aero, dict):
    telemetry = aero.get("telemetry")
    if isinstance(telemetry, dict):
        for key in ("fan_1_percent", "fan_2_percent"):
            value = telemetry.get(key)
            if value not in (None, 0):
                raise SystemExit(f"FAIL: {label}: AERO {key} is not 0%: {telemetry!r}")

print(f"PASS: {label}: STOP / 0 V / no observed fan motion")
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

stop_branch_web() {
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        kill "$WEB_PID" >/dev/null 2>&1 || true
        wait "$WEB_PID" 2>/dev/null || true
    fi
    WEB_PID=""
}

wait_branch_web_ready() {
    local attempt
    for attempt in $(seq 1 40); do
        if curl --silent --show-error --fail --max-time 2 \
            "$WEB_URL/api/v1/calendar" >/dev/null 2>&1; then
            return 0
        fi
        if [ -n "$WEB_PID" ] && ! kill -0 "$WEB_PID" 2>/dev/null; then
            echo "FAIL: branch WebGUI exited unexpectedly" >&2
            [ -f "$TEST_ROOT/web.log" ] && tail -n 80 "$TEST_ROOT/web.log" >&2 || true
            return 1
        fi
        sleep 0.25
    done
    echo "FAIL: branch WebGUI did not expose Calendar Engine endpoint" >&2
    [ -f "$TEST_ROOT/web.log" ] && tail -n 80 "$TEST_ROOT/web.log" >&2 || true
    return 1
}

start_branch_web() {
    env \
        PYTHONPATH="$WT/src" \
        PYTHONUNBUFFERED=1 \
        WVC_WEB_HOST=127.0.0.1 \
        WVC_WEB_PORT="$WEB_PORT" \
        WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock \
        WVC_WEB_TELEMETRY_DATABASE="$TEST_ROOT/telemetry.sqlite3" \
        WVC_WEB_ALERT_DATABASE="$TEST_ROOT/alerts.sqlite3" \
        WVC_WEB_WEATHER_SNAPSHOT="$TEST_ROOT/weather.json" \
        WVC_WEB_AI_ADVISORY_CACHE="$TEST_ROOT/ai-advisory.json" \
        /usr/bin/python3 -m ventilation_core.web.main \
        >"$TEST_ROOT/web.log" 2>&1 &
    WEB_PID=$!
    wait_branch_web_ready
    echo "PASS: isolated branch WebGUI ready on $WEB_URL (pid=$WEB_PID)"
}

write_core_dropin() {
    sudo install -d -m 0755 "$DROPIN_DIR"
    cat <<EOF | sudo tee "$DROPIN_PATH" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
ExecStart=
ExecStart=/usr/bin/python3 -m ventilation_core.main --socket /run/workshop-ventilation/ventilation-core.sock --alerts-db $TEST_ROOT/alerts.sqlite3 --automation-db $TEST_ROOT/automation.sqlite3 --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 --sensor-timeout 0.5 --sensor-poll-interval 1.0 --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 --aero-timeout 0.5 --aero-poll-interval 2.0 --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 --enable-supply-tacho --enable-extract-tacho --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 --tacho-timeout 0.25 --tacho-averaging-periods 6 --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt --zigbee-supply-name temp_nawiew --zigbee-supply-ieee 0xa4c13810e66fffff --zigbee-extract-name temp_wywiew --zigbee-extract-ieee 0xa4c13810bdedffff --zigbee-roles-file $TEST_ROOT/zigbee-roles.json --log-level INFO
EOF
    sudo chmod 0644 "$DROPIN_PATH"
}

restore_main_best_effort() {
    sudo rm -f "$DROPIN_PATH"
    sudo systemctl daemon-reload
    sudo systemctl restart "$UNIT"
    sleep 4
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    echo "===== CALENDAR ENGINE M3 EMERGENCY ROLLBACK =====" >&2
    stop_branch_web
    restore_main_best_effort
    if systemctl is-active --quiet "$UNIT"; then
        local pid
        pid="$(unit_pid)"
        echo "rollback core PID: $pid" >&2
        echo "rollback core CWD: $(unit_cwd "$pid" 2>/dev/null || true)" >&2
        require_safe_state "$ROOT/src" "rollback production main" >&2 || true
    else
        echo "CRITICAL: ventilation-core is not active after rollback attempt" >&2
    fi
    remove_worktree_best_effort
    echo "M3 diagnostic files preserved at: $TEST_ROOT" >&2
    exit "$rc"
}
trap emergency_rollback EXIT INT TERM

echo "===== CALENDAR ENGINE M3 CM5 VALIDATION ====="
cd "$ROOT"

[ "$(git branch --show-current)" = "main" ] || {
    echo "FAIL: production repo is not on main" >&2
    exit 1
}
[ -z "$(git status --short)" ] || {
    echo "FAIL: production main working tree is not clean" >&2
    exit 1
}
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: local main is not expected production base $EXPECTED_BASE" >&2
    exit 1
}
[ ! -e "$DROPIN_PATH" ] || {
    echo "FAIL: M3 validation drop-in already exists: $DROPIN_PATH" >&2
    exit 1
}

systemctl is-active --quiet "$UNIT" || {
    echo "FAIL: $UNIT is not active" >&2
    exit 1
}
MAIN_PID_BEFORE="$(unit_pid)"
[ "$(unit_cwd "$MAIN_PID_BEFORE")" = "$ROOT" ] || {
    echo "FAIL: production core is not running from main" >&2
    exit 1
}
require_safe_state "$ROOT/src" "preflight production main"

echo "===== FETCH PINNED SOURCES ====="
git fetch origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: origin/main changed from expected production base" >&2
    exit 1
}
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
echo "main:   $EXPECTED_BASE"
echo "branch: $BRANCH_SHA"

remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"

[ -f "$WT/tools/validate_calendar_engine_m3_cm5.py" ] || {
    echo "FAIL: M3 Python validator missing from branch" >&2
    exit 1
}

write_core_dropin
sudo systemctl daemon-reload
sudo systemctl restart "$UNIT"
sleep 5
systemctl is-active --quiet "$UNIT" || {
    echo "FAIL: Calendar Engine branch core did not become active" >&2
    exit 1
}
BRANCH_PID_PREPARE="$(unit_pid)"
[ "$BRANCH_PID_PREPARE" != "$MAIN_PID_BEFORE" ] || {
    echo "FAIL: core PID did not change for branch rollout" >&2
    exit 1
}
[ "$(unit_cwd "$BRANCH_PID_PREPARE")" = "$WT" ] || {
    echo "FAIL: core is not running from Calendar Engine worktree" >&2
    exit 1
}
require_safe_state "$WT/src" "branch core before Calendar Engine writes"

start_branch_web

echo "===== M3 PREPARE: SEMANTICS + WEBGUI ROUNDTRIP + SAFE RUNTIME ====="
env PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_calendar_engine_m3_cm5.py" \
    --phase prepare \
    --state-file "$STATE_FILE" \
    --web-url "$WEB_URL"

[ -s "$TEST_ROOT/automation.sqlite3" ] || {
    echo "FAIL: isolated Calendar Engine database was not created" >&2
    exit 1
}
require_safe_state "$WT/src" "branch core after Calendar Engine writes"

echo "===== M3 RESTART: PERSISTENCE TEST ====="
sudo systemctl restart "$UNIT"
sleep 5
systemctl is-active --quiet "$UNIT" || {
    echo "FAIL: branch core did not recover after persistence restart" >&2
    exit 1
}
BRANCH_PID_VERIFY="$(unit_pid)"
[ "$BRANCH_PID_VERIFY" != "$BRANCH_PID_PREPARE" ] || {
    echo "FAIL: core PID did not change during persistence restart" >&2
    exit 1
}
[ "$(unit_cwd "$BRANCH_PID_VERIFY")" = "$WT" ] || {
    echo "FAIL: restarted core is not running from Calendar Engine worktree" >&2
    exit 1
}
require_safe_state "$WT/src" "branch core after persistence restart"
wait_branch_web_ready

env PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_calendar_engine_m3_cm5.py" \
    --phase verify \
    --state-file "$STATE_FILE" \
    --web-url "$WEB_URL"

require_safe_state "$WT/src" "branch core after persistence verification"

echo "===== RESTORE PRODUCTION MAIN ====="
stop_branch_web
sudo rm -f "$DROPIN_PATH"
sudo systemctl daemon-reload
sudo systemctl restart "$UNIT"
sleep 5
systemctl is-active --quiet "$UNIT" || {
    echo "FAIL: production main core did not become active" >&2
    exit 1
}
MAIN_PID_AFTER="$(unit_pid)"
[ "$MAIN_PID_AFTER" != "$BRANCH_PID_VERIFY" ] || {
    echo "FAIL: core PID did not change while restoring main" >&2
    exit 1
}
[ "$(unit_cwd "$MAIN_PID_AFTER")" = "$ROOT" ] || {
    echo "FAIL: core did not return to production main CWD" >&2
    exit 1
}
require_safe_state "$ROOT/src" "final production main"

remove_worktree_best_effort
rm -rf "$TEST_ROOT"
trap - EXIT INT TERM

echo "PASS: Calendar Engine M3 validated on CM5 without ventilation/AERO control commands"
echo "branch SHA:        $BRANCH_SHA"
echo "main before PID:   $MAIN_PID_BEFORE"
echo "branch prepare PID:$BRANCH_PID_PREPARE"
echo "branch verify PID: $BRANCH_PID_VERIFY"
echo "main after PID:    $MAIN_PID_AFTER"
echo "final CWD:         $ROOT"
