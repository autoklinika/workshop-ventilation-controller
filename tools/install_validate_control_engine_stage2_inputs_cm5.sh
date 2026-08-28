#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-control-engine-stage2-validation
BRANCH=agent/automation-v1-control-engine
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE2_EXPECTED_BRANCH_SHA:-}"
CORE_UNIT=ventilation-core.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/99-zz-control-engine-stage2-validation.conf
TEST_ROOT=/var/tmp/wvc-control-engine-stage2-validation
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
SUPPLY_NAME=temp_nawiew
SUPPLY_IEEE=0xa4c13810e66fffff
EXTRACT_NAME=temp_wywiew
EXTRACT_IEEE=0xa4c13810bdedffff
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

assert_host_not_touched() {
    local label="$1"
    local boot_id host_pid wakealarm status_text
    boot_id="$(cat /proc/sys/kernel/random/boot_id)"
    host_pid="$(unit_pid wvc-host-power.service)"
    wakealarm="$(read_wakealarm)"
    [ "$boot_id" = "$BOOT_ID_BEFORE" ] || { echo "FAIL: $label: boot_id changed" >&2; exit 1; }
    [ "$host_pid" = "$HOST_POWER_PID_BEFORE" ] || { echo "FAIL: $label: host-power PID changed" >&2; exit 1; }
    [ "$wakealarm" = "$WAKEALARM_BEFORE" ] || { echo "FAIL: $label: RTC wakealarm changed" >&2; exit 1; }
    status_text="$(systemctl show wvc-host-power.service -p StatusText --value)"
    case "$status_text" in
        *"12 V domain ON"*) ;;
        *) echo "FAIL: $label: 12 V domain is not ON: $status_text" >&2; exit 1 ;;
    esac
    echo "PASS: $label: same boot, same host-power PID, unchanged RTC, 12 V domain ON"
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
    raise SystemExit(f"FAIL: {label}: logical EC setpoints are not 0 V: {sp!r}")
tacho = state.get("tacho") or {}
for channel in ("supply", "extract"):
    row = tacho.get(channel)
    if isinstance(row, dict) and float(row.get("rpm") or 0.0) != 0.0:
        raise SystemExit(f"FAIL: {label}: {channel} TACHO reports motion: {row!r}")
print(f"PASS: {label}: logical EC=0 V and no observed local fan motion")
PY
}

require_production_peripherals_ready() {
    local json
    json="$(ctl "$ROOT/src" status)"
    /usr/bin/python3 - "$json" <<'PY'
import json
import math
import sys

state = (json.loads(sys.argv[1]).get("state") or {})
if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
    raise SystemExit("FAIL: connect local DAC/hardware and ensure hardware_ready/output_state_known")

sensor_bus = state.get("sensor_bus") or {}
if sensor_bus.get("ready") is not True or sensor_bus.get("worker_alive") is not True:
    raise SystemExit("FAIL: SEN55 bus is not ready")
nodes = {row.get("slave_address"): row for row in sensor_bus.get("nodes") or [] if isinstance(row, dict)}
for address in (1, 2):
    node = nodes.get(address)
    if not node or not (
        node.get("online") is True
        and node.get("usable") is True
        and node.get("measurement_valid") is True
        and node.get("measurement_stale") is False
    ):
        raise SystemExit(f"FAIL: SEN55 node {address} is not fresh/usable")

zigbee = state.get("zigbee") or {}
if not (zigbee.get("running") is True and zigbee.get("connected") is True and zigbee.get("bridge_online") is True):
    raise SystemExit("FAIL: Zigbee MQTT/bridge is not healthy")
devices = {row.get("role"): row for row in zigbee.get("devices") or [] if isinstance(row, dict)}
for role in ("supply", "extract"):
    row = devices.get(role)
    if not row or row.get("available") is False:
        raise SystemExit(f"FAIL: Zigbee {role} role is missing/offline")
    value = row.get("temperature_celsius")
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SystemExit(f"FAIL: Zigbee {role} temperature is unavailable")

aero = state.get("aero_bus") or {}
if not (
    aero.get("ready") is True
    and aero.get("worker_alive") is True
    and aero.get("online") is True
    and aero.get("usable") is True
):
    raise SystemExit("FAIL: AERO is not ready/online/usable")

print("PASS: production peripherals ready: DAC + SEN55[1,2] + AERO + Zigbee supply/extract")
PY
}

check_real_inputs_and_shadow() {
    local json="$1"
    /usr/bin/python3 - "$json" <<'PY'
import json
import math
import sys

state = (json.loads(sys.argv[1]).get("state") or {})
if state.get("mode") != "STOP":
    raise SystemExit(f"WAIT: expected STOP mode, got {state.get('mode')!r}")
if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
    raise SystemExit("WAIT: hardware not ready/output state unknown")
for alarm in state.get("active_alarms") or []:
    if alarm.get("severity") == "critical":
        raise SystemExit(f"WAIT: critical alarm active: {alarm.get('code')!r}")

sensor_bus = state.get("sensor_bus") or {}
if sensor_bus.get("ready") is not True or sensor_bus.get("worker_alive") is not True:
    raise SystemExit("WAIT: SEN55 bus not ready")
nodes = {row.get("slave_address"): row for row in sensor_bus.get("nodes") or [] if isinstance(row, dict)}
for address in (1, 2):
    node = nodes.get(address)
    if not node:
        raise SystemExit(f"WAIT: SEN55 node {address} missing")
    if not (
        node.get("online") is True
        and node.get("usable") is True
        and node.get("measurement_valid") is True
        and node.get("measurement_stale") is False
    ):
        raise SystemExit(f"WAIT: SEN55 node {address} not fresh/usable")
    age = node.get("age_seconds")
    if age is None or float(age) > 15.0:
        raise SystemExit(f"WAIT: SEN55 node {address} age={age!r}")
    reading = node.get("reading") or {}
    for field in ("pm2_5_ug_m3", "pm10_0_ug_m3", "temperature_celsius", "voc_index", "nox_index"):
        value = reading.get(field)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise SystemExit(f"WAIT: SEN55 node {address} {field} unavailable: {value!r}")

aero = state.get("aero_bus") or {}
if not (
    aero.get("ready") is True
    and aero.get("worker_alive") is True
    and aero.get("online") is True
    and aero.get("usable") is True
):
    raise SystemExit("WAIT: AERO is not ready/online/usable")

zigbee = state.get("zigbee") or {}
if not (zigbee.get("running") is True and zigbee.get("connected") is True and zigbee.get("bridge_online") is True):
    raise SystemExit("WAIT: Zigbee MQTT/bridge not healthy")
devices = {
    row.get("role"): row
    for row in (zigbee.get("devices") or [])
    if isinstance(row, dict) and row.get("role") in {"supply", "extract"}
}
for role in ("supply", "extract"):
    device = devices.get(role)
    if not device:
        raise SystemExit(f"WAIT: Zigbee role {role} missing")
    if device.get("available") is False:
        raise SystemExit(f"WAIT: Zigbee role {role} offline")
    value = device.get("temperature_celsius")
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SystemExit(f"WAIT: Zigbee role {role} temperature unavailable")

shadow = state.get("shadow_automation") or {}
if shadow.get("actuation_supported") is not False:
    raise SystemExit("FAIL: Control Engine unexpectedly supports actuation")
if shadow.get("configuration_persistent") is not True:
    raise SystemExit("WAIT: persistent Control Engine configuration not active")
if shadow.get("status") not in {"TUNING_REQUIRED", "READY"}:
    raise SystemExit(f"WAIT: shadow status is {shadow.get('status')!r}")
zones = {row.get("sensor_address"): row for row in shadow.get("zones") or [] if isinstance(row, dict)}

pairs = {
    "sensor_pm2_5_ug_m3": "pm2_5_ug_m3",
    "sensor_pm10_0_ug_m3": "pm10_0_ug_m3",
    "sensor_voc_index": "voc_index",
    "sensor_nox_index": "nox_index",
    "sensor_temperature_celsius": "temperature_celsius",
}
for address in (1, 2):
    node = nodes[address]
    zone = zones.get(address)
    if not zone:
        raise SystemExit(f"FAIL: shadow zone for SEN55 address {address} missing")
    if not (
        zone.get("sensor_usable") is True
        and zone.get("sensor_online") is True
        and zone.get("sensor_measurement_valid") is True
        and zone.get("sensor_measurement_stale") is False
    ):
        raise SystemExit(f"FAIL: shadow provenance flags mismatch for SEN55 {address}")
    if zone.get("sensor_age_seconds") != node.get("age_seconds"):
        raise SystemExit(f"FAIL: SEN55 {address} age mismatch")
    if zone.get("sensor_last_success_at") != node.get("last_success_at"):
        raise SystemExit(f"FAIL: SEN55 {address} timestamp mismatch")
    reading = node["reading"]
    for shadow_field, sensor_field in pairs.items():
        if zone.get(shadow_field) != reading.get(sensor_field):
            raise SystemExit(
                f"FAIL: SEN55 {address} {shadow_field}={zone.get(shadow_field)!r} != {reading.get(sensor_field)!r}"
            )
    if zone.get("inside_temperature_celsius") != reading.get("temperature_celsius"):
        raise SystemExit(f"FAIL: SEN55 {address} consumed temperature mismatch")
    for field in ("pm2_5_level", "voc_level", "nox_level", "raw_air_quality_level", "air_quality_level"):
        if zone.get(field) is None:
            raise SystemExit(f"FAIL: SEN55 {address} shadow classification {field} missing")
    if zone.get("proposed_supply_voltage") is not None or zone.get("proposed_extract_voltage") is not None:
        raise SystemExit(f"FAIL: SEN55 {address} shadow exposed physical voltage proposal")

zone1 = zones[1]
supply = devices["supply"]
supply_temp = float(supply["temperature_celsius"])
if zone1.get("outside_temperature_usable") is not True:
    raise SystemExit("WAIT: Zigbee supply temperature not yet usable")
if zone1.get("outside_temperature_stale") is not False:
    raise SystemExit("WAIT: Zigbee supply temperature marked stale")
if zone1.get("outside_temperature_reason") != "OK":
    raise SystemExit(f"WAIT: Zigbee supply normalization reason={zone1.get('outside_temperature_reason')!r}")
if zone1.get("outside_temperature_celsius") != supply.get("temperature_celsius"):
    raise SystemExit("FAIL: Zigbee supply temperature mismatch between core and shadow")
inside_temp = float(nodes[1]["reading"]["temperature_celsius"])
expected_delta = inside_temp - supply_temp
actual_delta = zone1.get("temperature_delta_celsius")
if actual_delta is None or abs(float(actual_delta) - expected_delta) > 1e-6:
    raise SystemExit(f"FAIL: temperature delta mismatch: actual={actual_delta!r}, expected={expected_delta!r}")

if zone1.get("proposed_aero_speed") is not None:
    raise SystemExit("FAIL: fan zone unexpectedly proposes AERO speed")
if zones[2].get("proposed_aero_speed") is not None:
    raise SystemExit("FAIL: AERO zone should not propose speed while tuning is null")

print(json.dumps({
    "sen55_1": nodes[1]["reading"],
    "sen55_2": nodes[2]["reading"],
    "zigbee_supply_c": supply.get("temperature_celsius"),
    "zigbee_extract_c": devices["extract"].get("temperature_celsius"),
    "temperature_delta_c": actual_delta,
    "zone1_air_quality_level": zone1.get("air_quality_level"),
    "zone1_air_quality_driver": zone1.get("air_quality_driver"),
    "zone2_air_quality_level": zones[2].get("air_quality_level"),
    "zone2_air_quality_driver": zones[2].get("air_quality_driver"),
    "shadow_status": shadow.get("status"),
}, indent=2, sort_keys=True))
PY
}

wait_for_real_inputs() {
    local src="$1"
    local status_json="$TEST_ROOT/status.json"
    local result_file="$TEST_ROOT/input-check.txt"
    for _ in $(seq 1 120); do
        ctl "$src" status > "$status_json"
        if check_real_inputs_and_shadow "$(cat "$status_json")" > "$result_file" 2>&1; then
            cat "$result_file"
            return 0
        fi
        sleep 1
    done
    echo "FAIL: real-input readiness/SHADOW mapping did not validate" >&2
    cat "$result_file" >&2 || true
    return 1
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
    sleep 6
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    if [ "$ROLLOUT_STARTED" = "1" ]; then
        echo "===== CONTROL ENGINE STAGE2 EMERGENCY ROLLBACK =====" >&2
        restore_main_best_effort
    fi
    remove_worktree_best_effort
    echo "Stage2 diagnostic files preserved at: $TEST_ROOT" >&2
    exit "$rc"
}
trap emergency_rollback EXIT INT TERM

echo "===== CONTROL ENGINE V1 STAGE2 REAL INPUTS / SHADOW VALIDATION ====="
echo "REQUIRED: DAC + both SEN55 + AERO + Zigbee coordinator + supply/extract temperature sensors connected"
cd "$ROOT"

[ -n "$EXPECTED_BRANCH_SHA" ] || { echo "FAIL: CONTROL_ENGINE_STAGE2_EXPECTED_BRANCH_SHA is required" >&2; exit 1; }
[ "$(git branch --show-current)" = "main" ] || { echo "FAIL: production checkout is not main" >&2; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: production main is dirty" >&2; exit 1; }
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || { echo "FAIL: local main differs from expected production base" >&2; exit 1; }
systemctl is-active --quiet "$CORE_UNIT" || { echo "FAIL: ventilation-core is not active" >&2; exit 1; }
systemctl is-active --quiet wvc-host-power.service || { echo "FAIL: wvc-host-power is not active" >&2; exit 1; }
[ ! -e "$CORE_DROPIN" ] || { echo "FAIL: Stage2 core drop-in already exists" >&2; exit 1; }

MAIN_PID_BEFORE="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID_BEFORE")" = "$ROOT" ] || { echo "FAIL: production core is not running from main" >&2; exit 1; }
BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"
WAKEALARM_BEFORE="$(read_wakealarm)"
require_zero_output_guard "$ROOT/src" "production preflight"
require_production_peripherals_ready
assert_host_not_touched "preflight"

echo "===== FETCH PINNED CONTROL ENGINE SOURCES ====="
git fetch origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || { echo "FAIL: origin/main moved" >&2; exit 1; }
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: branch SHA $BRANCH_SHA differs from CI-tested $EXPECTED_BRANCH_SHA" >&2
    exit 1
}
remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"

if grep -q -- "--enable-scheduled-shutdown" "$WT/deploy/systemd/ventilation-core.service"; then
    echo "FAIL: production unit unexpectedly enables scheduled shutdown" >&2
    exit 1
fi

ROLLOUT_STARTED=1

echo "===== RUN PINNED BRANCH CORE WITH REAL INPUTS / SHADOW ONLY ====="
sudo install -d -m 0755 "$CORE_DROPIN_DIR"
cat <<EOF | sudo tee "$CORE_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=
ExecStart=/usr/bin/python3 -B -m ventilation_core.main --socket /run/workshop-ventilation/ventilation-core.sock --alerts-db $TEST_ROOT/alerts.sqlite3 --alert-policy $WT/config/alerts-v2.default.toml --automation-db $TEST_ROOT/automation.sqlite3 --system-power-command /usr/bin/vcgencmd --system-power-timeout 0.5 --power-scheduler-poll-interval 1.0 --power-scheduler-minimum-wake-lead 120 --rtc-agent-socket /run/wvc-rtc/rtc-wake.sock --rtc-agent-timeout 2.0 --host-power-socket /run/wvc-host-power/host-power.sock --host-power-timeout 10.0 --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 --sensor-timeout 0.5 --sensor-poll-interval 1.0 --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 --aero-timeout 0.5 --aero-poll-interval 2.0 --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 --enable-supply-tacho --enable-extract-tacho --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 --tacho-timeout 0.25 --tacho-averaging-periods 6 --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt --zigbee-supply-name $SUPPLY_NAME --zigbee-supply-ieee $SUPPLY_IEEE --zigbee-extract-name $EXTRACT_NAME --zigbee-extract-ieee $EXTRACT_IEEE --zigbee-roles-file $TEST_ROOT/zigbee-roles.json --log-level INFO
EOF
sudo systemctl daemon-reload
sudo systemctl restart "$CORE_UNIT"
sleep 6
systemctl is-active --quiet "$CORE_UNIT" || { echo "FAIL: branch core did not become active" >&2; exit 1; }
BRANCH_PID="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$BRANCH_PID")" = "$WT" ] || { echo "FAIL: branch core not running from pinned worktree" >&2; exit 1; }
require_zero_output_guard "$WT/src" "branch startup"
assert_host_not_touched "branch startup"

echo "===== WAIT FOR REAL SEN55 + AERO + ZIGBEE INPUTS AND VERIFY SHADOW MAPPING ====="
wait_for_real_inputs "$WT/src"
require_zero_output_guard "$WT/src" "after real-input validation"
assert_host_not_touched "after real-input validation"

echo "===== RESTORE PRODUCTION MAIN ====="
sudo rm -f "$CORE_DROPIN"
sudo systemctl daemon-reload
sudo systemctl restart "$CORE_UNIT"
sleep 6
systemctl is-active --quiet "$CORE_UNIT" || { echo "FAIL: production core did not recover" >&2; exit 1; }
MAIN_PID_AFTER="$(unit_pid "$CORE_UNIT")"
[ "$(unit_cwd "$MAIN_PID_AFTER")" = "$ROOT" ] || { echo "FAIL: production core not running from main after restore" >&2; exit 1; }
[ "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_BASE" ] || { echo "FAIL: production main HEAD changed" >&2; exit 1; }
[ -z "$(git -C "$ROOT" status --short)" ] || { echo "FAIL: production main became dirty" >&2; exit 1; }
require_zero_output_guard "$ROOT/src" "restored production main"
assert_host_not_touched "final production main"

ROLLOUT_STARTED=0
trap - EXIT INT TERM
remove_worktree_best_effort

echo "PASS: Control Engine V1 Stage2 real SEN55 + Zigbee inputs mapped 1:1 into SHADOW"
echo "PASS: AERO healthy; local EC remained 0 V; no physical Control Engine actuation occurred"
echo "PASS: RTC unchanged; host-power untouched; CM5 never rebooted/powered off"
echo "branch SHA:      $BRANCH_SHA"
echo "main before PID: $MAIN_PID_BEFORE"
echo "branch PID:      $BRANCH_PID"
echo "main after PID:  $MAIN_PID_AFTER"
echo "host-power PID:  $HOST_POWER_PID_BEFORE"
echo "boot_id:         $BOOT_ID_BEFORE"
