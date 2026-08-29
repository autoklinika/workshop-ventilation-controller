#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-webgui-automation-stage3-deployment
BRANCH=agent/web-gui-automation-stage3-deployment
EXPECTED_MAIN=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${WEBGUI_AUTOMATION_STAGE3_EXPECTED_BRANCH_SHA:-}"
CORE_UNIT=ventilation-core.service
WEB_UNIT=wvc-web-ui.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-webgui-automation-stage3-deployment.conf
WEB_DROPIN_DIR=/etc/systemd/system/${WEB_UNIT}.d
WEB_DROPIN=${WEB_DROPIN_DIR}/99-zz-webgui-automation-stage3-deployment.conf
TEST_ROOT=/var/tmp/wvc-webgui-automation-stage3-deployment
STATE_FILE=${TEST_ROOT}/stage3-state.json
PRODUCTION_AUTOMATION_DB=/var/lib/workshop-ventilation/automation.sqlite3
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
WEB_PORT=18091
WEB_URL=http://127.0.0.1:${WEB_PORT}
SUPPLY_NAME=temp_nawiew
SUPPLY_IEEE=0xa4c13810e66fffff
EXTRACT_NAME=temp_wywiew
EXTRACT_IEEE=0xa4c13810bdedffff
CORE_TOUCHED=0
WEB_TOUCHED=0
BOOT_ID_BEFORE=""
HOST_POWER_PID_BEFORE=""
HOST_POWER_STATUS_BEFORE=""
WAKEALARM_BEFORE=""
PRODUCTION_AUTOMATION_ROWS_BEFORE=""
WEB_ACTIVE_BEFORE=""
WEB_ENABLED_BEFORE=""
WEB_PORT_BEFORE=""

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

proc_env_var() {
    local pid="$1"
    local key="$2"
    /usr/bin/python3 - "$pid" "$key" <<'PY'
import sys
from pathlib import Path
pid, key = sys.argv[1], sys.argv[2]
try:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
except OSError:
    print("__UNAVAILABLE__")
    raise SystemExit(0)
prefix = (key + "=").encode()
for entry in raw.split(b"\0"):
    if entry.startswith(prefix):
        print(entry[len(prefix):].decode("utf-8", "replace"))
        break
else:
    print("__UNSET__")
PY
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
        raise SystemExit(f"FAIL: {label}: Control Engine gained actuation support")
    readiness = shadow.get("actuation_readiness") or {}
    if readiness.get("actuation_authorized") is not False:
        raise SystemExit(f"FAIL: {label}: actuation authority unexpectedly true")
    if readiness.get("ready") is not False:
        raise SystemExit(f"FAIL: {label}: readiness unexpectedly true")
print(f"PASS: {label}: EC=0 V / no observed fan motion" + (" / SHADOW non-actuating" if require_shadow else ""))
PY
}

assert_branch_core_runtime() {
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

dump_web_diagnostics() {
    local label="$1"
    echo "===== WEBGUI DIAGNOSTICS: $label =====" >&2
    systemctl status "$WEB_UNIT" --no-pager --full >&2 || true
    sudo journalctl -u "$WEB_UNIT" --no-pager -n 120 >&2 || true
}

wait_web_process_stable() {
    local label="$1"
    local attempt pid cwd
    for attempt in $(seq 1 80); do
        if systemctl is-active --quiet "$WEB_UNIT"; then
            pid="$(unit_pid "$WEB_UNIT" 2>/dev/null || true)"
            if [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ -d "/proc/$pid" ]; then
                cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
                if [ "$cwd" = "$WT" ]; then
                    return 0
                fi
            fi
        fi
        sleep 0.1
    done
    dump_web_diagnostics "$label"
    fail "$label: $WEB_UNIT did not reach a stable Stage3 process"
}

restart_web_checked() {
    local label="$1"
    if ! sudo systemctl restart "$WEB_UNIT"; then
        dump_web_diagnostics "$label restart command failed"
        fail "$label: systemctl restart $WEB_UNIT failed"
    fi
    wait_web_process_stable "$label"
}

wait_web_ready() {
    local attempt
    for attempt in $(seq 1 60); do
        if curl --silent --show-error --fail --max-time 2 "$WEB_URL/api/v1/state" >/dev/null 2>&1; then
            return 0
        fi
        if ! systemctl is-active --quiet "$WEB_UNIT"; then
            echo "FAIL: $WEB_UNIT exited while waiting for $WEB_URL" >&2
            dump_web_diagnostics "HTTP readiness"
            return 1
        fi
        sleep 0.25
    done
    echo "FAIL: $WEB_UNIT did not become ready at $WEB_URL" >&2
    dump_web_diagnostics "HTTP readiness timeout"
    return 1
}

assert_branch_web_runtime() {
    local label="$1"
    local pid cwd port socket pythonpath
    wait_web_process_stable "$label"
    pid="$(unit_pid "$WEB_UNIT" 2>/dev/null || true)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "$label: invalid WebGUI PID"
    cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
    [ "$cwd" = "$WT" ] || fail "$label: WebGUI CWD=$cwd expected=$WT"
    port="$(proc_env_var "$pid" WVC_WEB_PORT)"
    socket="$(proc_env_var "$pid" WVC_CORE_SOCKET)"
    pythonpath="$(proc_env_var "$pid" PYTHONPATH)"
    [ "$port" = "$WEB_PORT" ] || fail "$label: WVC_WEB_PORT=$port expected=$WEB_PORT"
    [ "$socket" = "/run/workshop-ventilation/ventilation-core.sock" ] || fail "$label: wrong core socket=$socket"
    [ "$pythonpath" = "$WT/src" ] || fail "$label: PYTHONPATH=$pythonpath expected=$WT/src"
    wait_web_ready
    echo "PASS: $label: real $WEB_UNIT runs Stage3 worktree as client on port $WEB_PORT (pid=$pid)"
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
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

write_web_dropin() {
    sudo install -d -m 0755 "$WEB_DROPIN_DIR"
    cat <<EOF | sudo tee "$WEB_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=WVC_WEB_HOST=127.0.0.1
Environment=WVC_WEB_PORT=$WEB_PORT
Environment=WVC_CORE_SOCKET=/run/workshop-ventilation/ventilation-core.sock
Environment=WVC_WEB_TELEMETRY_DATABASE=/srv/wvc-data/workshop-ventilation/telemetry.sqlite3
Environment=WVC_WEB_ALERT_DATABASE=/srv/wvc-data/workshop-ventilation/alerts.sqlite3
Environment=WVC_WEB_WEATHER_SNAPSHOT=/srv/wvc-data/workshop-ventilation/weather.json
Environment=WVC_WEB_AI_ADVISORY_CACHE=/srv/wvc-data/workshop-ventilation/ai-advisory.json
EnvironmentFile=
EOF
    sudo chmod 0644 "$WEB_DROPIN"
}

restore_production() {
    local rc="$1"
    set +e

    if [ "$WEB_TOUCHED" = "1" ]; then
        sudo systemctl stop "$WEB_UNIT" >/dev/null 2>&1 || true
    fi
    sudo rm -f "$WEB_DROPIN" "$CORE_DROPIN"
    sudo systemctl daemon-reload

    if [ "$CORE_TOUCHED" = "1" ]; then
        sudo systemctl restart "$CORE_UNIT"
        sleep 6
    fi

    remove_worktree_best_effort

    if [ "$WEB_TOUCHED" = "1" ]; then
        if [ "$WEB_ACTIVE_BEFORE" = "active" ]; then
            sudo systemctl restart "$WEB_UNIT"
            sleep 1
        else
            sudo systemctl stop "$WEB_UNIT" >/dev/null 2>&1 || true
        fi
    fi

    if [ "$CORE_TOUCHED" = "1" ]; then
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
            echo "CRITICAL: production automation SQLite rows changed during isolated WebGUI Stage3" >&2
            echo "before: $PRODUCTION_AUTOMATION_ROWS_BEFORE" >&2
            echo "after:  $production_rows_after" >&2
            rc=1
        else
            echo "PASS: production Calendar/Control Engine SQLite rows unchanged by isolated Stage3"
        fi
        assert_host_untouched "rollback production main" || rc=1
    fi

    if [ "$(systemctl is-enabled "$WEB_UNIT" 2>/dev/null || true)" != "$WEB_ENABLED_BEFORE" ]; then
        echo "CRITICAL: $WEB_UNIT enablement changed during Stage3" >&2
        rc=1
    fi
    if [ "$WEB_ACTIVE_BEFORE" = "active" ]; then
        if ! systemctl is-active --quiet "$WEB_UNIT"; then
            echo "CRITICAL: production $WEB_UNIT was active before Stage3 but is not active after rollback" >&2
            rc=1
        else
            local web_pid web_cwd web_port_after
            web_pid="$(unit_pid "$WEB_UNIT")"
            web_cwd="$(unit_cwd "$web_pid" 2>/dev/null || true)"
            web_port_after="$(proc_env_var "$web_pid" WVC_WEB_PORT)"
            if [ "$web_cwd" != "$ROOT" ]; then
                echo "CRITICAL: production WebGUI CWD=$web_cwd expected=$ROOT" >&2
                rc=1
            fi
            if [ "$web_port_after" != "$WEB_PORT_BEFORE" ]; then
                echo "CRITICAL: production WebGUI port environment changed: before=$WEB_PORT_BEFORE after=$web_port_after" >&2
                rc=1
            else
                echo "PASS: production $WEB_UNIT restored with original port environment=$WEB_PORT_BEFORE"
            fi
        fi
    else
        if systemctl is-active --quiet "$WEB_UNIT"; then
            echo "CRITICAL: production $WEB_UNIT was inactive before Stage3 but is active after rollback" >&2
            rc=1
        else
            echo "PASS: production $WEB_UNIT restored to inactive state"
        fi
    fi

    if [ "$(git -C "$ROOT" branch --show-current)" != "main" ] || \
       [ "$(git -C "$ROOT" rev-parse HEAD)" != "$EXPECTED_MAIN" ] || \
       [ -n "$(git -C "$ROOT" status --short)" ]; then
        echo "CRITICAL: production main checkout changed during Stage3" >&2
        rc=1
    else
        echo "PASS: production main remains clean at $EXPECTED_MAIN"
    fi

    exit "$rc"
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    restore_production "$rc"
}
trap emergency_rollback EXIT INT TERM

[ -n "$EXPECTED_BRANCH_SHA" ] || fail "set WEBGUI_AUTOMATION_STAGE3_EXPECTED_BRANCH_SHA to exact CI-tested branch SHA"

cd "$ROOT"
echo "===== WEBGUI AUTOMATION STAGE3 SYSTEMD CLIENT CM5 VALIDATION ====="
echo "INFO: WebGUI is only a client; authoritative logic and safety remain in ventilation-core"
echo "INFO: real wvc-web-ui.service on port 18091 + real branch core + isolated automation DB"

echo "===== 1. PIN PRODUCTION / SNAPSHOT CLIENT AND SAFETY STATE ====="
[ "$(git branch --show-current)" = "main" ] || fail "production checkout is not on main"
[ "$(git rev-parse HEAD)" = "$EXPECTED_MAIN" ] || fail "local main is not expected production SHA"
[ -z "$(git status --short)" ] || fail "production main working tree is dirty"
[ ! -e "$CORE_DROPIN" ] || fail "Stage3 core drop-in already exists: $CORE_DROPIN"
[ ! -e "$WEB_DROPIN" ] || fail "Stage3 WebGUI drop-in already exists: $WEB_DROPIN"

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
systemctl cat "$WEB_UNIT" >/dev/null 2>&1 || fail "$WEB_UNIT is not installed"
WEB_ACTIVE_BEFORE="$(systemctl is-active "$WEB_UNIT" 2>/dev/null || true)"
[ "$WEB_ACTIVE_BEFORE" = "active" ] || [ "$WEB_ACTIVE_BEFORE" = "inactive" ] || fail "$WEB_UNIT preflight state=$WEB_ACTIVE_BEFORE; expected active or inactive"
WEB_ENABLED_BEFORE="$(systemctl is-enabled "$WEB_UNIT" 2>/dev/null || true)"
if [ "$WEB_ACTIVE_BEFORE" = "active" ]; then
    WEB_PID_BEFORE="$(unit_pid "$WEB_UNIT")"
    [ "$(unit_cwd "$WEB_PID_BEFORE")" = "$ROOT" ] || fail "production WebGUI does not run from main"
    WEB_PORT_BEFORE="$(proc_env_var "$WEB_PID_BEFORE" WVC_WEB_PORT)"
else
    WEB_PORT_BEFORE="__INACTIVE__"
fi
MAIN_PID_BEFORE="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID_BEFORE")" = "$ROOT" ] || fail "production core does not run from main"
BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"
HOST_POWER_STATUS_BEFORE="$(systemctl show wvc-host-power.service -p StatusText --value)"
WAKEALARM_BEFORE="$(read_wakealarm)"
PRODUCTION_AUTOMATION_ROWS_BEFORE="$(read_production_automation_rows)"
require_zero_output "$ROOT/src" "production preflight" 0
assert_host_untouched "production preflight"

echo "PASS: production WebGUI state=$WEB_ACTIVE_BEFORE enabled=$WEB_ENABLED_BEFORE port-env=$WEB_PORT_BEFORE"

echo "===== 2. EXACT STAGE3 WORKTREE / ISOLATED REAL CORE ====="
remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"
[ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ] || fail "worktree SHA mismatch"
[ -f "$WT/tools/validate_web_gui_automation_stage3_deployment_cm5.py" ] || fail "Stage3 validator missing"
[ -f "$WT/tools/apply_validated_control_engine_tacho_confirmation.py" ] || fail "validated TACHO patcher missing"
[ "$(env PYTHONPATH="$WT/src" /usr/bin/python3 -B -c 'from ventilation_core.web.main import DEFAULT_PORT; print(DEFAULT_PORT)')" = "$WEB_PORT" ] || fail "Stage3 WebGUI default port is not $WEB_PORT"
if grep -q -- "--enable-scheduled-shutdown" "$WT/deploy/systemd/ventilation-core.service"; then
    fail "production unit unexpectedly enables scheduled shutdown"
fi

WEB_TOUCHED=1
sudo systemctl stop "$WEB_UNIT" >/dev/null 2>&1 || true
write_core_dropin
sudo systemctl daemon-reload
CORE_TOUCHED=1
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_core_runtime "branch core startup"
require_zero_output "$WT/src" "branch core startup" 1
assert_host_untouched "branch core startup"

echo "===== 3. APPLY ONLY PHYSICALLY VALIDATED 4.0s TO ISOLATED CONTROL ENGINE ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 -B "$WT/tools/apply_validated_control_engine_tacho_confirmation.py" \
    --confirm-apply >/dev/null
sleep 1
require_zero_output "$WT/src" "after isolated 4.0 s config" 1
assert_host_untouched "after isolated 4.0 s config"

echo "===== 4. START REAL wvc-web-ui.service AS STAGE3 CLIENT ON 18091 ====="
write_web_dropin
sudo systemctl daemon-reload
restart_web_checked "Stage3 WebGUI startup"
assert_branch_web_runtime "Stage3 WebGUI startup"
require_zero_output "$WT/src" "after Stage3 WebGUI startup" 1
assert_host_untouched "after Stage3 WebGUI startup"

echo "===== 5. CLIENT ROUND-TRIP THROUGH REAL SYSTEMD WEBGUI ====="
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src:$WT/tools" \
    /usr/bin/python3 -B "$WT/tools/validate_web_gui_automation_stage3_deployment_cm5.py" \
    --phase prepare \
    --web-url "$WEB_URL" \
    --state-file "$STATE_FILE"
require_zero_output "$WT/src" "after Stage3 client round-trip" 1
assert_host_untouched "after Stage3 client round-trip"

echo "===== 6. RESTART WEBGUI CLIENT ONLY: CORE-OWNED STATE MUST NOT CHANGE ====="
CORE_PID_BEFORE_WEB_RESTART="$(unit_pid "$CORE_UNIT")"
restart_web_checked "WebGUI-only restart"
assert_branch_web_runtime "after WebGUI-only restart"
[ "$(unit_pid "$CORE_UNIT")" = "$CORE_PID_BEFORE_WEB_RESTART" ] || fail "WebGUI restart unexpectedly restarted authoritative core"
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src:$WT/tools" \
    /usr/bin/python3 -B "$WT/tools/validate_web_gui_automation_stage3_deployment_cm5.py" \
    --phase web-restart \
    --web-url "$WEB_URL" \
    --state-file "$STATE_FILE"
require_zero_output "$WT/src" "after WebGUI-only restart" 1
assert_host_untouched "after WebGUI-only restart"

echo "===== 7. RESTART AUTHORITATIVE CORE: CLIENT SURVIVES / CORE SEMANTICS OWN STATE ====="
WEB_PID_BEFORE_CORE_RESTART="$(unit_pid "$WEB_UNIT")"
sudo systemctl restart "$CORE_UNIT"
sleep 6
assert_branch_core_runtime "after authoritative core restart"
require_zero_output "$WT/src" "after authoritative core restart" 1
[ "$(unit_pid "$WEB_UNIT")" = "$WEB_PID_BEFORE_CORE_RESTART" ] || fail "core restart unexpectedly restarted independent WebGUI client"
assert_branch_web_runtime "WebGUI after core restart"
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src:$WT/tools" \
    /usr/bin/python3 -B "$WT/tools/validate_web_gui_automation_stage3_deployment_cm5.py" \
    --phase core-restart \
    --web-url "$WEB_URL" \
    --state-file "$STATE_FILE"
require_zero_output "$WT/src" "after Stage3 core-restart verification" 1
assert_host_untouched "after Stage3 core-restart verification"

echo "===== 8. RESULT ====="
echo "PASS: WebGUI Automation Stage3 runs through the real wvc-web-ui.service on port 18091"
echo "PASS: WebGUI remained only a client of authoritative ventilation-core"
echo "PASS: WebGUI operator writes used the core-enforced SHADOW-only contract"
echo "PASS: WebGUI-only restart preserved core-owned operator/calendar state"
echo "PASS: core restart reset volatile operator to AUTO revision 0 while Calendar persisted"
echo "PASS: physical EC/AERO remained stopped; actuation authority remained absent; readiness=false"
echo "PASS: production automation SQLite rows will be checked unchanged during rollback"
echo "branch SHA:       $BRANCH_SHA"
echo "production SHA:   $EXPECTED_MAIN"
echo "WebGUI port:      $WEB_PORT"
echo "WebGUI unit:      $WEB_UNIT"

trap - EXIT INT TERM
restore_production 0
