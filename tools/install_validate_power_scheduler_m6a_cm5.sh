#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-power-m6a-validation
BRANCH=agent/automation-v1-scheduler-assumptions
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${M6A_EXPECTED_BRANCH_SHA:-}"
LAB_MODE="${M6A_LAB_MODE:-0}"
CORE_UNIT=ventilation-core.service
RTC_UNIT=wvc-rtc-wake-m6a.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-power-m6a-validation.conf
RTC_UNIT_PATH=/etc/systemd/system/${RTC_UNIT}
TEST_ROOT=/var/tmp/wvc-power-m6a-validation
RTC_SOCKET=/run/wvc-rtc/rtc-wake.sock
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
ROLLOUT_STARTED=0
BRANCH_SHA=""
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
    env PYTHONPATH="$src" /usr/bin/python3 -m ventilation_core.ctl "$@"
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
    raise SystemExit(f"FAIL: {label}: status request failed: {doc!r}")
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

require_m6_disabled_runtime() {
    local label="$1"
    local json
    json="$(ctl "$WT/src" status)"
    /usr/bin/python3 - "$label" "$json" <<'PY'
import json
import sys

label = sys.argv[1]
doc = json.loads(sys.argv[2])
if doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: core status failed: {doc!r}")
state = doc.get("state") or {}
power = state.get("power_scheduler")
if not isinstance(power, dict):
    raise SystemExit(f"FAIL: {label}: power_scheduler projection missing")
expected = {
    "scheduled_shutdown_enabled": False,
    "shutdown_ready": False,
    "rtc_alarm_armed": False,
    "rtc_alarm_verified": False,
    "rtc_alarm_value": None,
    "shutdown_inhibited_reason": "scheduled_shutdown_disabled",
    "last_host_power_requested": False,
    "last_host_power_accepted": False,
}
for key, value in expected.items():
    if power.get(key) != value:
        raise SystemExit(
            f"FAIL: {label}: power_scheduler.{key}={power.get(key)!r}, expected {value!r}"
        )
if power.get("worker_alive") is not True:
    raise SystemExit(f"FAIL: {label}: Power Scheduler worker is not alive")
if not power.get("last_tick_at"):
    raise SystemExit(f"FAIL: {label}: worker has not completed a disabled-mode tick")
alert_v2 = state.get("alert_v2") or {}
if alert_v2.get("policy_version") != "2026-08-27.1":
    raise SystemExit(
        f"FAIL: {label}: AlertV2 policy version is {alert_v2.get('policy_version')!r}"
    )
if alert_v2.get("alert_count") != 52:
    raise SystemExit(f"FAIL: {label}: AlertV2 alert_count={alert_v2.get('alert_count')!r}")
if alert_v2.get("control_policy_applied") is not False:
    raise SystemExit(f"FAIL: {label}: AlertV2 unexpectedly applies control policy")
print(
    f"PASS: {label}: M6 runtime alive, scheduled shutdown disabled, "
    "RTC unarmed, host-power untouched, AlertV2 M6 policy loaded"
)
PY
}

assert_host_not_touched() {
    local label="$1"
    local boot_id host_pid wakealarm
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
    local status_text
    status_text="$(systemctl show wvc-host-power.service -p StatusText --value)"
    case "$status_text" in
        *"12 V domain ON"*) ;;
        *) echo "FAIL: $label: host-power does not report 12 V domain ON: $status_text" >&2; exit 1 ;;
    esac
    echo "PASS: $label: same boot, same host-power PID, unchanged RTC, 12 V domain ON"
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

stop_temp_rtc_best_effort() {
    sudo systemctl stop "$RTC_UNIT" >/dev/null 2>&1 || true
    sudo rm -f "$RTC_UNIT_PATH"
    sudo systemctl daemon-reload >/dev/null 2>&1 || true
}

restore_main_best_effort() {
    sudo rm -f "$CORE_DROPIN"
    stop_temp_rtc_best_effort
    sudo systemctl daemon-reload
    sudo systemctl restart "$CORE_UNIT"
    sleep 5
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        echo "===== POWER SCHEDULER M6A EMERGENCY ROLLBACK =====" >&2
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
        echo "M6A stopped before rollout; production ventilation-core was not restarted by cleanup" >&2
    fi
    remove_worktree_best_effort
    echo "M6A diagnostic files preserved at: $TEST_ROOT" >&2
    exit "$rc"
}
trap emergency_rollback EXIT INT TERM

echo "===== POWER SCHEDULER M6A CM5 NON-ACTUATING VALIDATION ====="
cd "$ROOT"

case "$LAB_MODE" in
    0|1) ;;
    *) echo "FAIL: M6A_LAB_MODE must be 0 or 1" >&2; exit 1 ;;
esac
[ -n "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: M6A_EXPECTED_BRANCH_SHA must pin the exact CI-tested branch commit" >&2
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
    echo "FAIL: M6A core validation drop-in already exists: $CORE_DROPIN" >&2
    exit 1
}
[ ! -e "$RTC_UNIT_PATH" ] || {
    echo "FAIL: temporary M6A RTC unit already exists: $RTC_UNIT_PATH" >&2
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
    echo "INFO: M6A LAB mode enabled; disconnected DAC/SEN55/AERO may leave core in FAULT/output_state_unknown"
fi
require_safe_state "$ROOT/src" "preflight production main"
assert_host_not_touched "preflight"

echo "===== FETCH PINNED M6 SOURCES ====="
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

[ -f "$WT/src/ventilation_core/rtc_wake_agent.py" ] || {
    echo "FAIL: M6 RTC wake agent missing from branch" >&2
    exit 1
}
[ -f "$WT/src/ventilation_core/application/power_scheduler_runtime.py" ] || {
    echo "FAIL: M6 Power Scheduler runtime missing from branch" >&2
    exit 1
}

ROLLOUT_STARTED=1

echo "===== START TEMPORARY BRANCH RTC AGENT ====="
cat <<EOF | sudo tee "$RTC_UNIT_PATH" >/dev/null
[Unit]
Description=Workshop Ventilation M6A Temporary RTC Wake Agent
After=local-fs.target

[Service]
Type=simple
User=root
Group=wentylacja
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
RuntimeDirectory=wvc-rtc
RuntimeDirectoryMode=0770
UMask=0007
ExecStart=/usr/bin/python3 -m ventilation_core.rtc_wake_agent --socket $RTC_SOCKET --wakealarm $WAKEALARM --log-level INFO
Restart=on-failure
RestartSec=2
TimeoutStopSec=5
NoNewPrivileges=true
RestrictAddressFamilies=AF_UNIX
EOF
sudo chmod 0644 "$RTC_UNIT_PATH"
sudo systemctl daemon-reload
sudo systemctl start "$RTC_UNIT"
sleep 2
systemctl is-active --quiet "$RTC_UNIT" || {
    echo "FAIL: temporary RTC wake agent did not become active" >&2
    exit 1
}
[ -S "$RTC_SOCKET" ] || {
    echo "FAIL: temporary RTC wake agent socket missing: $RTC_SOCKET" >&2
    exit 1
}
assert_host_not_touched "after RTC agent start"

echo "===== RUN BRANCH CORE WITH SCHEDULED SHUTDOWN DISABLED ====="
sudo install -d -m 0755 "$CORE_DROPIN_DIR"
cat <<EOF | sudo tee "$CORE_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
ExecStart=
ExecStart=/usr/bin/python3 -m ventilation_core.main --socket /run/workshop-ventilation/ventilation-core.sock --alerts-db $TEST_ROOT/alerts.sqlite3 --alert-policy $WT/config/alerts-v2.default.toml --automation-db $TEST_ROOT/automation.sqlite3 --system-power-command /usr/bin/vcgencmd --system-power-timeout 0.5 --power-scheduler-poll-interval 1.0 --power-scheduler-minimum-wake-lead 120 --rtc-agent-socket $RTC_SOCKET --rtc-agent-timeout 2.0 --host-power-socket /run/wvc-host-power/host-power.sock --host-power-timeout 10.0 --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 --sensor-timeout 0.5 --sensor-poll-interval 1.0 --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 --aero-timeout 0.5 --aero-poll-interval 2.0 --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 --enable-supply-tacho --enable-extract-tacho --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 --tacho-timeout 0.25 --tacho-averaging-periods 6 --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt --zigbee-supply-name temp_nawiew --zigbee-supply-ieee 0xa4c13810e66fffff --zigbee-extract-name temp_wywiew --zigbee-extract-ieee 0xa4c13810bdedffff --zigbee-roles-file $TEST_ROOT/zigbee-roles.json --log-level INFO
EOF
sudo chmod 0644 "$CORE_DROPIN"
sudo systemctl daemon-reload
sudo systemctl restart "$CORE_UNIT"
sleep 4
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: M6 branch core did not become active" >&2
    exit 1
}
BRANCH_PID_1="$(unit_pid "$CORE_UNIT")"
[ "$BRANCH_PID_1" != "$MAIN_PID_BEFORE" ] || {
    echo "FAIL: core PID did not change for M6 rollout" >&2
    exit 1
}
[ "$(unit_cwd "$BRANCH_PID_1")" = "$WT" ] || {
    echo "FAIL: core is not running from M6 worktree" >&2
    exit 1
}
require_safe_state "$WT/src" "M6 branch core first boot"
require_m6_disabled_runtime "M6 branch core first boot"
assert_host_not_touched "M6 branch first boot"

echo "===== RESTART BRANCH CORE: M6 LIFECYCLE ====="
sudo systemctl restart "$CORE_UNIT"
sleep 4
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: M6 branch core did not recover after restart" >&2
    exit 1
}
BRANCH_PID_2="$(unit_pid "$CORE_UNIT")"
[ "$BRANCH_PID_2" != "$BRANCH_PID_1" ] || {
    echo "FAIL: core PID did not change during M6 lifecycle restart" >&2
    exit 1
}
[ "$(unit_cwd "$BRANCH_PID_2")" = "$WT" ] || {
    echo "FAIL: restarted core is not running from M6 worktree" >&2
    exit 1
}
require_safe_state "$WT/src" "M6 branch core after restart"
require_m6_disabled_runtime "M6 branch core after restart"
assert_host_not_touched "M6 branch after restart"

echo "===== RESTORE PRODUCTION MAIN ====="
sudo rm -f "$CORE_DROPIN"
stop_temp_rtc_best_effort
sudo systemctl daemon-reload
sudo systemctl restart "$CORE_UNIT"
sleep 5
systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: production main core did not become active" >&2
    exit 1
}
MAIN_PID_AFTER="$(unit_pid "$CORE_UNIT")"
[ "$MAIN_PID_AFTER" != "$BRANCH_PID_2" ] || {
    echo "FAIL: core PID did not change while restoring main" >&2
    exit 1
}
[ "$(unit_cwd "$MAIN_PID_AFTER")" = "$ROOT" ] || {
    echo "FAIL: core did not return to production main CWD" >&2
    exit 1
}
require_safe_state "$ROOT/src" "final production main"
assert_host_not_touched "final production main"

ROLLOUT_STARTED=0
remove_worktree_best_effort
rm -rf "$TEST_ROOT"
trap - EXIT INT TERM

echo "PASS: Power Scheduler M6A runtime validated on CM5 with scheduled shutdown disabled"
echo "PASS: RTC wakealarm unchanged; host-power never requested; CM5 never rebooted/powered off"
echo "lab mode:        $LAB_MODE"
echo "branch SHA:      $BRANCH_SHA"
echo "main before PID: $MAIN_PID_BEFORE"
echo "branch PID #1:   $BRANCH_PID_1"
echo "branch PID #2:   $BRANCH_PID_2"
echo "main after PID:  $MAIN_PID_AFTER"
echo "host-power PID:  $HOST_POWER_PID_BEFORE"
echo "boot_id:         $BOOT_ID_BEFORE"
