#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-control-engine-stage1-validation
BRANCH=agent/automation-v1-control-engine
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_EXPECTED_BRANCH_SHA:-}"
LAB_MODE="${CONTROL_ENGINE_LAB_MODE:-0}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-control-engine-stage1-validation.conf
TEST_ROOT=/var/tmp/wvc-control-engine-stage1-validation
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
ROLLOUT_STARTED=0
BOOT_ID_BEFORE=""
HOST_POWER_PID_BEFORE=""
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

require_safe_state() {
    local src="$1"
    local label="$2"
    local json
    json="$(ctl "$src" status)"
    /usr/bin/python3 - "$label" "$json" "$LAB_MODE" <<'PY'
import json
import sys

label = sys.argv[1]
doc = json.loads(sys.argv[2])
lab_mode = sys.argv[3] == "1"
if doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: core status failed: {doc!r}")
state = doc.get("state") or {}
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC logical setpoints are not 0 V: {sp!r}")
mode = state.get("mode")
if lab_mode:
    if mode not in {"STOP", "FAULT"}:
        raise SystemExit(f"FAIL: {label}: LAB mode accepts only STOP/FAULT, got {mode!r}")
else:
    if mode != "STOP":
        raise SystemExit(f"FAIL: {label}: mode is not STOP: {mode!r}")
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
print(f"PASS: {label}: logical EC=0 V and no observed fan motion")
PY
}

assert_host_not_touched() {
    local label="$1"
    local boot_id host_pid wakealarm status_text
    boot_id="$(cat /proc/sys/kernel/random/boot_id)"
    host_pid="$(unit_pid wvc-host-power.service)"
    wakealarm="$(read_wakealarm)"
    [ "$boot_id" = "$BOOT_ID_BEFORE" ] || {
        echo "FAIL: $label: boot_id changed unexpectedly" >&2
        exit 1
    }
    [ "$host_pid" = "$HOST_POWER_PID_BEFORE" ] || {
        echo "FAIL: $label: wvc-host-power PID changed unexpectedly" >&2
        exit 1
    }
    [ "$wakealarm" = "$WAKEALARM_BEFORE" ] || {
        echo "FAIL: $label: RTC wakealarm changed unexpectedly: before='$WAKEALARM_BEFORE' now='$wakealarm'" >&2
        exit 1
    }
    status_text="$(systemctl show wvc-host-power.service -p StatusText --value)"
    case "$status_text" in
        *"12 V domain ON"*) ;;
        *) echo "FAIL: $label: host-power does not report 12 V domain ON: $status_text" >&2; exit 1 ;;
    esac
    echo "PASS: $label: same boot, same host-power PID, unchanged RTC, 12 V domain ON"
}

require_control_engine_state() {
    local expected_revision="$1"
    local expected_version="$2"
    local label="$3"
    local config_json state_json
    config_json="$(ctl "$WT/src" control-engine)"
    state_json="$(ctl "$WT/src" status)"
    /usr/bin/python3 - "$expected_revision" "$expected_version" "$label" "$config_json" "$state_json" <<'PY'
import json
import sys

revision = int(sys.argv[1])
version = sys.argv[2]
label = sys.argv[3]
config_doc = json.loads(sys.argv[4])
state_doc = json.loads(sys.argv[5])

if config_doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: control-engine read failed: {config_doc!r}")
ce = config_doc.get("control_engine") or {}
if ce.get("revision") != revision:
    raise SystemExit(f"FAIL: {label}: revision={ce.get('revision')!r}, expected {revision}")
if ce.get("actuation_supported") is not False:
    raise SystemExit(f"FAIL: {label}: control-engine claims actuation support")
config = ce.get("config") or {}
policy = config.get("policy") or {}
if policy.get("version") != version:
    raise SystemExit(
        f"FAIL: {label}: policy.version={policy.get('version')!r}, expected {version!r}"
    )
if "actuation_enabled" in config or "actuation_enabled" in policy:
    raise SystemExit(f"FAIL: {label}: persistent configuration exposes actuation_enabled")

tuning = policy.get("tuning") or {}
if any(value is not None for value in tuning.values()):
    raise SystemExit(f"FAIL: {label}: validation tuning must remain entirely null: {tuning!r}")

if state_doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: status failed: {state_doc!r}")
shadow = (state_doc.get("state") or {}).get("shadow_automation") or {}
if shadow.get("actuation_supported") is not False:
    raise SystemExit(f"FAIL: {label}: shadow actuation_supported is not false")
if shadow.get("configuration_revision") != revision:
    raise SystemExit(
        f"FAIL: {label}: shadow configuration_revision={shadow.get('configuration_revision')!r}"
    )
if shadow.get("configuration_persistent") is not True:
    raise SystemExit(f"FAIL: {label}: shadow configuration_persistent is not true")
for zone in shadow.get("zones") or []:
    if zone.get("proposed_supply_voltage") is not None:
        raise SystemExit(f"FAIL: {label}: proposed_supply_voltage must remain null")
    if zone.get("proposed_extract_voltage") is not None:
        raise SystemExit(f"FAIL: {label}: proposed_extract_voltage must remain null")
print(
    f"PASS: {label}: persistent revision={revision}, version={version}, "
    "all tuning null, actuation unsupported"
)
PY
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        sudo find "$WT" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        sudo find "$WT" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

restore_main_best_effort() {
    sudo rm -f "$CORE_DROPIN"
    sudo systemctl daemon-reload
    sudo systemctl restart "$CORE_UNIT"
    sleep 5
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        echo "===== CONTROL ENGINE STAGE1 EMERGENCY ROLLBACK =====" >&2
        restore_main_best_effort
        if systemctl is-active --quiet "$CORE_UNIT"; then
            local pid
            pid="$(unit_pid "$CORE_UNIT")"
            echo "rollback core PID: $pid" >&2
            echo "rollback core CWD: $(unit_cwd "$pid" 2>/dev/null || true)" >&2
            require_safe_state "$ROOT/src" "rollback production main" >&2 || true
        else
            echo "CRITICAL: ventilation-core is not active after rollback attempt" >&2
        fi
    else
        echo "Control Engine validation stopped before rollout; production core was not restarted by cleanup" >&2
    fi
    remove_worktree_best_effort
    echo "Control Engine diagnostic files preserved at: $TEST_ROOT" >&2
    exit "$rc"
}
trap emergency_rollback EXIT INT TERM

echo "===== CONTROL ENGINE V1 STAGE1 CM5 NON-ACTUATING VALIDATION ====="
cd "$ROOT"

case "$LAB_MODE" in
    0|1) ;;
    *) echo "FAIL: CONTROL_ENGINE_LAB_MODE must be 0 or 1" >&2; exit 1 ;;
esac
[ -n "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: CONTROL_ENGINE_EXPECTED_BRANCH_SHA must pin exact CI-tested branch commit" >&2
    exit 1
}
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
[ ! -e "$CORE_DROPIN" ] || {
    echo "FAIL: Control Engine validation drop-in already exists: $CORE_DROPIN" >&2
    exit 1
}
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: $CORE_UNIT is not active" >&2
    exit 1
}
systemctl is-active --quiet wvc-host-power.service || {
    echo "FAIL: wvc-host-power.service is not active" >&2
    exit 1
}

MAIN_PID_BEFORE="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID_BEFORE")" = "$ROOT" ] || {
    echo "FAIL: production core is not running from main" >&2
    exit 1
}
BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"
WAKEALARM_BEFORE="$(read_wakealarm)"
if [ "$LAB_MODE" = "1" ]; then
    echo "INFO: LAB mode enabled; disconnected DAC/SEN55/AERO may leave core in FAULT/output_state_unknown"
fi
require_safe_state "$ROOT/src" "preflight production main"
assert_host_not_touched "preflight"

echo "===== FETCH PINNED CONTROL ENGINE SOURCES ====="
git fetch origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: origin/main changed from expected production base" >&2
    exit 1
}
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: fetched branch SHA $BRANCH_SHA differs from CI-tested $EXPECTED_BRANCH_SHA" >&2
    exit 1
}
echo "main:   $EXPECTED_BASE"
echo "branch: $BRANCH_SHA"

remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"

[ -f "$WT/src/ventilation_core/application/control_engine_runtime.py" ] || {
    echo "FAIL: persistent Control Engine runtime missing from branch" >&2
    exit 1
}
[ -f "$WT/src/ventilation_core/runtime/control_engine_server.py" ] || {
    echo "FAIL: Control Engine core socket extension missing from branch" >&2
    exit 1
}
if grep -q -- "--enable-scheduled-shutdown" "$WT/deploy/systemd/ventilation-core.service"; then
    echo "FAIL: production systemd unit unexpectedly enables scheduled shutdown" >&2
    exit 1
fi

ROLLOUT_STARTED=1

echo "===== RUN BRANCH CORE — CONTROL ENGINE SHADOW ONLY ====="
sudo install -d -m 0755 "$CORE_DROPIN_DIR"
cat <<EOF | sudo tee "$CORE_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=
ExecStart=/usr/bin/python3 -B -m ventilation_core.main --socket /run/workshop-ventilation/ventilation-core.sock --alerts-db $TEST_ROOT/alerts.sqlite3 --alert-policy $WT/config/alerts-v2.default.toml --automation-db $TEST_ROOT/automation.sqlite3 --system-power-command /usr/bin/vcgencmd --system-power-timeout 0.5 --power-scheduler-poll-interval 1.0 --power-scheduler-minimum-wake-lead 120 --rtc-agent-socket /run/wvc-rtc/rtc-wake.sock --rtc-agent-timeout 2.0 --host-power-socket /run/wvc-host-power/host-power.sock --host-power-timeout 10.0 --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 --sensor-timeout 0.5 --sensor-poll-interval 1.0 --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 --aero-timeout 0.5 --aero-poll-interval 2.0 --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 --enable-supply-tacho --enable-extract-tacho --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 --tacho-timeout 0.25 --tacho-averaging-periods 6 --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt --zigbee-supply-name temp_nawiew --zigbee-extract-name temp_wywiew --zigbee-roles-file $TEST_ROOT/zigbee-roles.json --log-level INFO
EOF
sudo systemctl daemon-reload
sudo systemctl restart "$CORE_UNIT"
sleep 6
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: branch ventilation-core did not become active" >&2
    exit 1
}
BRANCH_PID_1="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$BRANCH_PID_1")" = "$WT" ] || {
    echo "FAIL: branch core is not running from pinned worktree" >&2
    exit 1
}
require_safe_state "$WT/src" "Control Engine branch first boot"
assert_host_not_touched "Control Engine branch first boot"
require_control_engine_state 1 "shadow-policy-v1-2026-08-12" "initial persistent configuration"

echo "===== HOT RELOAD CONFIGURATION — VERSION ONLY / ALL TUNING NULL ====="
ctl "$WT/src" control-engine > "$TEST_ROOT/control-engine-before.json"
/usr/bin/python3 - "$TEST_ROOT/control-engine-before.json" "$TEST_ROOT/control-engine-v2.json" <<'PY'
import json
import sys

source, target = sys.argv[1:]
doc = json.load(open(source, encoding="utf-8"))
config = doc["control_engine"]["config"]
if any(value is not None for value in config["policy"]["tuning"].values()):
    raise SystemExit("FAIL: initial tuning is not entirely null")
config["policy"]["version"] = "control-engine-stage1-cm5-validation"
with open(target, "w", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
ctl "$WT/src" control-engine-replace --file "$TEST_ROOT/control-engine-v2.json" \
    > "$TEST_ROOT/control-engine-replace.json"
/usr/bin/python3 - "$TEST_ROOT/control-engine-replace.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
ce = doc.get("control_engine") or {}
if doc.get("ok") is not True or ce.get("revision") != 2:
    raise SystemExit(f"FAIL: hot replace response invalid: {doc!r}")
if ce.get("dynamics_reset") is not True:
    raise SystemExit("FAIL: hot replace did not report dynamics_reset=true")
if ce.get("actuation_supported") is not False:
    raise SystemExit("FAIL: hot replace unexpectedly claims actuation support")
print("PASS: hot reload accepted revision=2 and remained non-actuating")
PY
require_control_engine_state 2 "control-engine-stage1-cm5-validation" "after hot reload"
require_safe_state "$WT/src" "after Control Engine hot reload"
assert_host_not_touched "after Control Engine hot reload"

echo "===== RESTART BRANCH CORE — VERIFY CONFIG PERSISTENCE ====="
sudo systemctl restart "$CORE_UNIT"
sleep 6
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: branch core failed after lifecycle restart" >&2
    exit 1
}
BRANCH_PID_2="$(unit_pid "$CORE_UNIT")"
[ "$BRANCH_PID_2" != "$BRANCH_PID_1" ] || {
    echo "FAIL: branch core PID did not change across restart" >&2
    exit 1
}
[ "$(unit_cwd "$BRANCH_PID_2")" = "$WT" ] || {
    echo "FAIL: restarted branch core is not running from pinned worktree" >&2
    exit 1
}
require_control_engine_state 2 "control-engine-stage1-cm5-validation" "after branch core restart"
require_safe_state "$WT/src" "Control Engine branch after restart"
assert_host_not_touched "Control Engine branch after restart"

echo "===== RESTORE PRODUCTION MAIN ====="
sudo rm -f "$CORE_DROPIN"
sudo systemctl daemon-reload
sudo systemctl restart "$CORE_UNIT"
sleep 6
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: production core did not recover" >&2
    exit 1
}
MAIN_PID_AFTER="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID_AFTER")" = "$ROOT" ] || {
    echo "FAIL: production core is not running from main after restore" >&2
    exit 1
}
[ "$(git -C "$ROOT" branch --show-current)" = "main" ] || {
    echo "FAIL: production checkout is not main after validation" >&2
    exit 1
}
[ "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: production main HEAD changed during validation" >&2
    exit 1
}
[ -z "$(git -C "$ROOT" status --short)" ] || {
    echo "FAIL: production main working tree changed during validation" >&2
    exit 1
}
require_safe_state "$ROOT/src" "final production main"
assert_host_not_touched "final production main"

ROLLOUT_STARTED=0
trap - EXIT INT TERM
remove_worktree_best_effort

echo "PASS: Control Engine V1 Stage1 persistent SHADOW runtime validated on CM5"
echo "PASS: hot reload + restart persistence verified; all tuning stayed null"
echo "PASS: RTC unchanged; host-power untouched; CM5 never rebooted/powered off"
echo "lab mode:        $LAB_MODE"
echo "branch SHA:      $BRANCH_SHA"
echo "main before PID: $MAIN_PID_BEFORE"
echo "branch PID #1:   $BRANCH_PID_1"
echo "branch PID #2:   $BRANCH_PID_2"
echo "main after PID:  $MAIN_PID_AFTER"
echo "host-power PID:  $HOST_POWER_PID_BEFORE"
echo "boot_id:         $BOOT_ID_BEFORE"
