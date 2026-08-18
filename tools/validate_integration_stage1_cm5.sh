#!/usr/bin/env bash
set -Eeuo pipefail

PROD="/home/wentylacja/workshop-ventilation-controller"
WT="/home/wentylacja/workshop-ventilation-integration-stage1"
BRANCH="agent/integration-stage1"

CORE_SERVICE="ventilation-core.service"
TELEMETRY_SERVICE="wvc-telemetry-sync.service"
WEB_SERVICE="wvc-web-ui.service"

TEST_SOCKET="/tmp/wvc-integration-stage1.sock"
TEST_AUTOMATION_DB="/tmp/wvc-integration-stage1-automation.sqlite3"
TEST_ALERTS_DB="/tmp/wvc-integration-stage1-alerts.sqlite3"
TEST_HISTORY_DB="/tmp/wvc-integration-stage1-telemetry.sqlite3"
TEST_ZIGBEE_ROLES="/tmp/wvc-integration-stage1-zigbee-roles.json"
TEST_CORE_LOG="/tmp/wvc-integration-stage1-core.log"
TEST_WEB_LOG="/tmp/wvc-integration-stage1-web.log"
TEST_WEB_PORT=18094

TEST_CORE_PID=""
TEST_WEB_PID=""
VALIDATION_PASS=0
CORE_PAUSED=0
TELEMETRY_PAUSED=0
WEB_PAUSED=0
ROLE_STORE_HASH_BEFORE=""

prod_ctl() {
    PYTHONPATH="$PROD/src" python3 -m ventilation_core.ctl \
        --socket /run/workshop-ventilation/ventilation-core.sock "$@"
}

test_ctl() {
    PYTHONPATH="$WT/src" python3 -m ventilation_core.ctl \
        --socket "$TEST_SOCKET" "$@"
}

service_state() {
    systemctl is-active "$1" 2>/dev/null || true
}

CORE_WAS_ACTIVE="$(service_state "$CORE_SERVICE")"
TELEMETRY_WAS_ACTIVE="$(service_state "$TELEMETRY_SERVICE")"
WEB_WAS_ACTIVE="$(service_state "$WEB_SERVICE")"

stop_test_web() {
    if [ -n "${TEST_WEB_PID:-}" ] && kill -0 "$TEST_WEB_PID" 2>/dev/null; then
        kill -TERM "$TEST_WEB_PID" 2>/dev/null || true
        wait "$TEST_WEB_PID" 2>/dev/null || true
    fi
    TEST_WEB_PID=""
}

stop_test_core() {
    if [ -n "${TEST_CORE_PID:-}" ] && kill -0 "$TEST_CORE_PID" 2>/dev/null; then
        test_ctl shutdown >/dev/null 2>&1 || true
        for _ in $(seq 1 20); do
            if ! kill -0 "$TEST_CORE_PID" 2>/dev/null; then break; fi
            sleep 0.5
        done
        if kill -0 "$TEST_CORE_PID" 2>/dev/null; then
            kill -TERM "$TEST_CORE_PID" 2>/dev/null || true
        fi
        wait "$TEST_CORE_PID" 2>/dev/null || true
    fi
    TEST_CORE_PID=""
    rm -f "$TEST_SOCKET"
}

wait_production_core() {
    local ready=0
    for _ in $(seq 1 40); do
        if [ "$(service_state "$CORE_SERVICE")" = "active" ] && \
           prod_ctl status >/tmp/wvc-integration-production-restored.json 2>/dev/null; then
            if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-production-restored.json'))['state']
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
z=s.get('zigbee')
if z is not None:
    assert z['connected'] is True
    assert z['bridge_online'] is True
PY
            then
                ready=1
                break
            fi
        fi
        sleep 1
    done
    [ "$ready" = "1" ]
}

restore_production() {
    local rc="$1"
    local restore_ok=1
    set +e

    stop_test_web
    stop_test_core

    echo
    echo "===== RESTORE PRODUKCJI ====="
    if [ "$CORE_PAUSED" = "1" ]; then
        sudo systemctl start "$CORE_SERVICE" || restore_ok=0
        if [ "$restore_ok" = "1" ] && wait_production_core; then
            if prod_ctl stop >/tmp/wvc-integration-production-stop.json 2>/dev/null; then
                python3 - <<'PY' || restore_ok=0
import json
s=json.load(open('/tmp/wvc-integration-production-stop.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
print('production core: STOP / 0 V / hardware ready: PASS')
PY
            else
                restore_ok=0
            fi
        else
            restore_ok=0
        fi
    fi

    if [ "$TELEMETRY_PAUSED" = "1" ]; then sudo systemctl start "$TELEMETRY_SERVICE" || restore_ok=0; fi
    if [ "$WEB_PAUSED" = "1" ]; then sudo systemctl start "$WEB_SERVICE" || restore_ok=0; fi

    if [ -n "$ROLE_STORE_HASH_BEFORE" ] && [ -f /var/lib/workshop-ventilation/zigbee-roles.json ]; then
        ROLE_STORE_HASH_AFTER="$(sha256sum /var/lib/workshop-ventilation/zigbee-roles.json | awk '{print $1}')"
        if [ "$ROLE_STORE_HASH_AFTER" != "$ROLE_STORE_HASH_BEFORE" ]; then
            echo "BŁĄD: produkcyjny rejestr ról Zigbee został zmieniony przez walidację."
            restore_ok=0
        else
            echo "production Zigbee role registry unchanged: PASS"
        fi
    fi

    echo "core:      $(service_state "$CORE_SERVICE")"
    echo "telemetry: $(service_state "$TELEMETRY_SERVICE")"
    echo "web V2:    $(service_state "$WEB_SERVICE")"

    if [ "$restore_ok" != "1" ]; then
        echo "BŁĄD KRYTYCZNY: nie udało się jednoznacznie przywrócić produkcji."
        rc=1
    fi

    if [ "$rc" = "0" ] && [ "$VALIDATION_PASS" = "1" ]; then
        echo
        echo "========================================================"
        echo "INTEGRATION STAGE 1 — CM5 LAB VALIDATION: PASS"
        echo "========================================================"
        echo "Zigbee:                    PASS"
        echo "schedule + SHADOW:         PASS"
        echo "history capture/API:       PASS"
        echo "GUI settings integration:  PASS"
        echo "real hardware:              PASS"
        echo "actuation during test:      NONE / STOP 0 V"
        echo "production restored:        PASS"
        echo "========================================================"
    fi
    return "$rc"
}

cleanup() {
    local rc=$?
    trap - EXIT
    restore_production "$rc"
    exit $?
}
trap cleanup EXIT

wait_test_core() {
    local ready=0
    for _ in $(seq 1 40); do
        if [ -n "${TEST_CORE_PID:-}" ] && kill -0 "$TEST_CORE_PID" 2>/dev/null && \
           test_ctl status >/tmp/wvc-integration-test-state.json 2>/dev/null; then
            if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-test-state.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True and s['output_state_known'] is True
sb=s['sensor_bus']; assert sb and sb['ready'] is True and sb['worker_alive'] is True
nodes={int(n['slave_address']):n for n in sb['nodes']}
assert set(nodes)=={1,2}
assert all(n['online'] is True and n['usable'] is True for n in nodes.values())
a=s['aero_bus']; assert a and a['ready'] is True and a['online'] is True and a['usable'] is True
t=s['tacho']; assert t and t['ready'] is True and t['worker_alive'] is True
schedule=s['schedule']; assert schedule and schedule['available'] is True
shadow=s['shadow_automation']; assert shadow and shadow['enabled'] is True and shadow['actuation_supported'] is False
z=s['zigbee']; assert z and z['connected'] is True and z['bridge_online'] is True
assert z['permit_join'] is False
inventory=[d for d in z['inventory'] if not d['is_coordinator']]
assert len(inventory) == 3, inventory
rows={d['friendly_name']:d for d in z['sensor_list']}
assert {'temp_nawiew','temp_wywiew','temp_zew'} <= set(rows), rows
assert rows['temp_nawiew']['role']=='supply'
assert rows['temp_wywiew']['role']=='extract'
assert rows['temp_zew']['role']=='other'
assert rows['temp_nawiew']['temperature_celsius'] is not None
assert rows['temp_wywiew']['temperature_celsius'] is not None
assert rows['temp_zew']['temperature_celsius'] is not None
PY
            then
                ready=1
                break
            fi
        fi
        sleep 1
    done
    if [ "$ready" != "1" ]; then
        echo "BŁĄD: zintegrowany testowy core nie osiągnął oczekiwanego stanu."
        cat "$TEST_CORE_LOG" 2>/dev/null || true
        test_ctl status 2>/dev/null || true
        return 1
    fi
}

start_test_core() {
    rm -f "$TEST_SOCKET"
    env PYTHONPATH="$WT/src" PYTHONUNBUFFERED=1 \
        python3 -m ventilation_core.main \
            --bus 1 --address 0x58 \
            --socket "$TEST_SOCKET" \
            --alerts-db "$TEST_ALERTS_DB" \
            --automation-db "$TEST_AUTOMATION_DB" \
            --minimum-running-voltage 1.0 --maximum-voltage 10.0 \
            --command-timeout 3.0 --health-interval 1.0 --hardware-failure-threshold 3 \
            --sensor-port /dev/ttyAMA0 --sensor-addresses 1,2 --sensor-baud 19200 \
            --sensor-timeout 0.5 --sensor-poll-interval 1.0 \
            --sensor-inter-node-delay 0.010 --sensor-reconnect-delay 1.0 \
            --aero-port /dev/ttyAMA4 --aero-address 44 --aero-baud 9600 \
            --aero-timeout 0.5 --aero-poll-interval 2.0 \
            --aero-inter-register-delay 0.050 --aero-reconnect-delay 1.0 \
            --enable-supply-tacho --enable-extract-tacho \
            --tacho-chip /dev/gpiochip0 --supply-tacho-line GPIO17 --extract-tacho-line GPIO27 \
            --tacho-timeout 0.25 --tacho-averaging-periods 6 \
            --zigbee-mqtt-host 127.0.0.1 --zigbee-mqtt-port 1883 --zigbee-base-topic zigbee2mqtt \
            --zigbee-supply-name temp_nawiew --zigbee-supply-ieee 0xa4c13810e66fffff \
            --zigbee-extract-name temp_wywiew --zigbee-extract-ieee 0xa4c13810bdedffff \
            --zigbee-roles-file "$TEST_ZIGBEE_ROLES" \
            --log-level INFO >"$TEST_CORE_LOG" 2>&1 &
    TEST_CORE_PID=$!
    wait_test_core
}

start_test_web() {
    env PYTHONPATH="$WT/src" PYTHONUNBUFFERED=1 \
        python3 -m ventilation_core.web.main \
            --host 127.0.0.1 --port "$TEST_WEB_PORT" \
            --socket "$TEST_SOCKET" --telemetry-database "$TEST_HISTORY_DB" \
            >"$TEST_WEB_LOG" 2>&1 &
    TEST_WEB_PID=$!
    local ready=0
    for _ in $(seq 1 20); do
        if kill -0 "$TEST_WEB_PID" 2>/dev/null && \
           curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/health" >/dev/null 2>&1; then
            ready=1; break
        fi
        sleep 0.5
    done
    if [ "$ready" != "1" ]; then
        echo "BŁĄD: testowy Web GUI nie wystartował."
        cat "$TEST_WEB_LOG" 2>/dev/null || true
        return 1
    fi
}

echo "========================================================"
echo "INTEGRATION STAGE 1 — CM5 LAB VALIDATION"
echo "========================================================"

echo
echo "===== 1. PRECHECK ====="
sudo -v
test "$CORE_WAS_ACTIVE" = "active"
test -d "$PROD/.git" -o -f "$PROD/.git"
test -d "$WT/.git" -o -f "$WT/.git"
cd "$WT"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "BŁĄD: worktree ma lokalne tracked zmiany."; git status --short; exit 1
fi
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
HEAD="$(git rev-parse HEAD)"
echo "HEAD: $HEAD"

echo
echo "===== 2. PEŁNY TEST SUITE ====="
PYTHONWARNINGS="error::ResourceWarning" PYTHONPATH=src python3 -m unittest discover -s tests

echo
echo "===== 3. PRODUKCJA PRZED PRZEŁĄCZENIEM ====="
prod_ctl status >/tmp/wvc-integration-production-before.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-production-before.json'))['state']
assert s['mode']=='STOP'
assert float(s['setpoints']['supply_voltage'])==0.0
assert float(s['setpoints']['extract_voltage'])==0.0
assert s['hardware_ready'] is True and s['output_state_known'] is True
z=s.get('zigbee'); assert z and z['connected'] is True and z['bridge_online'] is True
assert z['permit_join'] is False
print('production STOP / 0 V + Zigbee online: PASS')
PY

ROLE_STORE_HASH_BEFORE="$(sha256sum /var/lib/workshop-ventilation/zigbee-roles.json | awk '{print $1}')"
cp /var/lib/workshop-ventilation/zigbee-roles.json "$TEST_ZIGBEE_ROLES"

rm -f "$TEST_SOCKET" \
    "$TEST_AUTOMATION_DB" "$TEST_AUTOMATION_DB-wal" "$TEST_AUTOMATION_DB-shm" \
    "$TEST_ALERTS_DB" "$TEST_ALERTS_DB-wal" "$TEST_ALERTS_DB-shm" \
    "$TEST_HISTORY_DB" "$TEST_HISTORY_DB-wal" "$TEST_HISTORY_DB-shm" \
    "$TEST_CORE_LOG" "$TEST_WEB_LOG"

if [ "$TELEMETRY_WAS_ACTIVE" = "active" ]; then sudo systemctl stop "$TELEMETRY_SERVICE"; TELEMETRY_PAUSED=1; fi
if [ "$WEB_WAS_ACTIVE" = "active" ]; then sudo systemctl stop "$WEB_SERVICE"; WEB_PAUSED=1; fi
prod_ctl stop >/dev/null
sudo systemctl stop "$CORE_SERVICE"
CORE_PAUSED=1
test "$(service_state "$CORE_SERVICE")" != "active"
echo "production services safely paused: PASS"

echo
echo "===== 4. ZINTEGROWANY CORE + REAL HARDWARE + ZIGBEE ====="
start_test_core
test_ctl status >/tmp/wvc-integration-ready.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-ready.json'))['state']
z=s['zigbee']; rows={x['friendly_name']:x for x in z['sensor_list']}
print('SENSOR/AERO/TACHO: PASS')
print('Zigbee inventory/sensor_list/roles/retained telemetry: PASS')
print('temp_nawiew:', rows['temp_nawiew']['temperature_celsius'])
print('temp_wywiew:', rows['temp_wywiew']['temperature_celsius'])
print('temp_zew:', rows['temp_zew']['temperature_celsius'], 'RH', rows['temp_zew']['humidity_percent'])
PY

echo
echo "===== 5. SCHEDULE + SHADOW W TYM SAMYM CORE ====="
python3 - <<'PY'
import json
from datetime import datetime
from zoneinfo import ZoneInfo
weekday=datetime.now(ZoneInfo('Europe/Warsaw')).isoweekday()
window=[{'weekday':weekday,'start_local':'00:00','end_local':'23:59','expectation':'OCCUPIED_EXPECTED','enabled':True,'label':'INTEGRATION E2E'}]
for p in ('/tmp/wvc-integration-zone1.json','/tmp/wvc-integration-zone2.json'):
    json.dump(window,open(p,'w'))
print('weekday:',weekday)
PY
test_ctl schedule-replace --zone zone-1 --file /tmp/wvc-integration-zone1.json >/dev/null
test_ctl schedule-replace --zone zone-2 --file /tmp/wvc-integration-zone2.json >/dev/null
sleep 0.5
test_ctl status >/tmp/wvc-integration-scheduled.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-scheduled.json'))['state']
assert s['mode']=='STOP' and float(s['setpoints']['supply_voltage'])==0 and float(s['setpoints']['extract_voltage'])==0
sh=s['shadow_automation']; assert sh['enabled'] is True and sh['actuation_supported'] is False
assert sh['policy_version']=='shadow-policy-v1-2026-08-12'
assert sh['tuning_complete'] is False
zones={z['zone']:z for z in sh['zones']}
assert all(z['schedule_expectation']=='OCCUPIED_EXPECTED' for z in zones.values())
assert all(z['sensor_usable'] is True for z in zones.values())
assert s['zigbee']['connected'] is True
print('schedule + SHADOW + Zigbee coexist in one CoreState: PASS')
print('SHADOW non-actuating / outputs STOP 0 V: PASS')
PY

echo
echo "===== 6. TELEMETRY CAPTURE Z PEŁNYM CORESTATE ====="
env PYTHONPATH="$WT/src" WVC_AI_BRIDGE_URL= WVC_TELEMETRY_SOURCE_ID=integration-cm5 \
    python3 -m ventilation_core.telemetry.main \
        --socket "$TEST_SOCKET" --database "$TEST_HISTORY_DB" --once
python3 - <<'PY'
import json,sqlite3
p='/tmp/wvc-integration-stage1-telemetry.sqlite3'
con=sqlite3.connect(p); row=con.execute('select metrics_json from telemetry_samples order by sequence desc limit 1').fetchone(); con.close()
assert row
m=json.loads(row[0])
assert m['zigbee']['connected'] is True
assert len(m['zigbee']['sensor_list']) >= 3
assert m['schedule']['available'] is True
assert m['shadow_automation']['enabled'] is True
assert m['shadow_automation']['actuation_supported'] is False
assert m['sensor_bus']['ready'] is True
print('full integrated CoreState persisted locally: PASS')
PY

echo
echo "===== 7. WEB API + WSPÓLNE USTAWIENIA ====="
start_test_web
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/state" >/tmp/wvc-integration-web-state.json
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/zigbee" >/tmp/wvc-integration-web-zigbee.json
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/schedule" >/tmp/wvc-integration-web-schedule.json
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/history/status" >/tmp/wvc-integration-web-history.json
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/settings" >/tmp/wvc-integration-settings.html
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/zigbee-settings.js" >/dev/null
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/schedule.js" >/dev/null
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-web-state.json'))['state']
assert s['zigbee']['connected'] is True
assert s['schedule']['available'] is True
assert s['shadow_automation']['enabled'] is True
z=json.load(open('/tmp/wvc-integration-web-zigbee.json')); assert z['ok'] is True and len(z['zigbee']['sensor_list']) >= 3
sc=json.load(open('/tmp/wvc-integration-web-schedule.json')); assert sc['ok'] is True and sc['schedule']['available'] is True
h=json.load(open('/tmp/wvc-integration-web-history.json')); assert h['ok'] is True and h['history']['available'] is True
html=open('/tmp/wvc-integration-settings.html').read()
assert 'id="zigbeeSettingsMount"' in html
assert 'src="/zigbee-settings.js"' in html
assert 'data-zone-editor="zone-1"' in html and 'data-zone-editor="zone-2"' in html
assert 'src="/schedule.js"' in html
print('Web state/Zigbee/schedule/history APIs: PASS')
print('one /settings page contains Zigbee + schedule editors: PASS')
PY

echo
echo "===== 8. BRAK MUTACJI ZIGBEE / BRAK AKTUACJI ====="
test_ctl status >/tmp/wvc-integration-final.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-integration-final.json'))['state']
assert s['mode']=='STOP'
assert float(s['setpoints']['supply_voltage'])==0.0
assert float(s['setpoints']['extract_voltage'])==0.0
assert s['zigbee']['permit_join'] is False
assert len([x for x in s['zigbee']['inventory'] if not x['is_coordinator']])==3
print('STOP / 0 V: PASS')
print('permit_join=false, 3 devices remain paired: PASS')
PY

VALIDATION_PASS=1
echo
echo "===== WALIDACJA INTEGRACYJNA ZAKOŃCZONA ====="
echo "cleanup przywróci produkcyjny core, telemetrię i GUI V2."
