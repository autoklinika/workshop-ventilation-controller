#!/usr/bin/env bash
set -Eeuo pipefail

PROD="/home/wentylacja/workshop-ventilation-controller"
WT="/home/wentylacja/workshop-ventilation-history-stage1"
BRANCH="agent/schedules-history-automation-stage1"

CORE_SERVICE="ventilation-core.service"
TELEMETRY_SERVICE="wvc-telemetry-sync.service"
WEB_SERVICE="wvc-web-ui.service"

TEST_SOCKET="/tmp/wvc-history-shadow-stage1.sock"
TEST_AUTOMATION_DB="/tmp/wvc-history-shadow-stage1-automation.sqlite3"
TEST_ALERTS_DB="/tmp/wvc-history-shadow-stage1-alerts.sqlite3"
TEST_HISTORY_DB="/tmp/wvc-history-shadow-stage1-telemetry.sqlite3"
TEST_CORE_LOG="/tmp/wvc-history-shadow-stage1-core.log"
TEST_WEB_LOG="/tmp/wvc-history-shadow-stage1-web.log"
TEST_WEB_PORT=18093
TEST_CORE_PID=""
TEST_WEB_PID=""
VALIDATION_PASS=0
CORE_PAUSED=0
TELEMETRY_PAUSED=0
WEB_PAUSED=0

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
            if ! kill -0 "$TEST_CORE_PID" 2>/dev/null; then
                break
            fi
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
    for _ in $(seq 1 30); do
        if [ "$(service_state "$CORE_SERVICE")" = "active" ] && \
           prod_ctl status >/tmp/wvc-history-shadow-production-restored.json 2>/dev/null; then
            if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-history-shadow-production-restored.json'))['state']
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
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
            if prod_ctl stop >/tmp/wvc-history-shadow-production-stop.json 2>/dev/null; then
                python3 - <<'PY' || restore_ok=0
import json
s=json.load(open('/tmp/wvc-history-shadow-production-stop.json'))['state']
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

    if [ "$TELEMETRY_PAUSED" = "1" ]; then
        sudo systemctl start "$TELEMETRY_SERVICE" || restore_ok=0
    fi
    if [ "$WEB_PAUSED" = "1" ]; then
        sudo systemctl start "$WEB_SERVICE" || restore_ok=0
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
        echo "HISTORY + SHADOW STAGE 1 — CM5 E2E VALIDATION: PASS"
        echo "========================================================"
        echo "produkcyjny core:       PRZYWRÓCONY"
        echo "produkcyjny stan:       STOP / 0 V"
        echo "produkcyjna automation: NIE ZMIENIANA"
        echo "produkcyjna telemetria: PRZYWRÓCONA"
        echo "produkcyjny GUI V2:     PRZYWRÓCONY"
        echo "test telemetry DB:      $TEST_HISTORY_DB"
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
    for _ in $(seq 1 30); do
        if [ -n "${TEST_CORE_PID:-}" ] && kill -0 "$TEST_CORE_PID" 2>/dev/null && \
           test_ctl status >/tmp/wvc-history-shadow-test-state.json 2>/dev/null; then
            if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-history-shadow-test-state.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
sb=s['sensor_bus']
assert sb is not None and sb['ready'] is True and sb['worker_alive'] is True
nodes={int(n['slave_address']):n for n in sb['nodes']}
assert set(nodes) == {1,2}
assert all(n['online'] is True and n['usable'] is True for n in nodes.values())
a=s['aero_bus']
assert a is not None and a['ready'] is True and a['worker_alive'] is True
assert a['online'] is True and a['usable'] is True
t=s['tacho']
assert t is not None and t['ready'] is True and t['worker_alive'] is True
shadow=s['shadow_automation']
assert shadow is not None
assert shadow['enabled'] is True
assert shadow['actuation_supported'] is False
PY
            then
                ready=1
                break
            fi
        fi
        sleep 1
    done
    if [ "$ready" != "1" ]; then
        echo "BŁĄD: testowy core nie osiągnął oczekiwanego stanu."
        cat "$TEST_CORE_LOG" 2>/dev/null || true
        return 1
    fi
}

start_test_core() {
    rm -f "$TEST_SOCKET"
    env \
        PYTHONPATH="$WT/src" \
        PYTHONUNBUFFERED=1 \
        python3 -m ventilation_core.main \
            --bus 1 \
            --address 0x58 \
            --socket "$TEST_SOCKET" \
            --alerts-db "$TEST_ALERTS_DB" \
            --automation-db "$TEST_AUTOMATION_DB" \
            --minimum-running-voltage 1.0 \
            --maximum-voltage 10.0 \
            --command-timeout 3.0 \
            --health-interval 1.0 \
            --hardware-failure-threshold 3 \
            --sensor-port /dev/ttyAMA0 \
            --sensor-addresses 1,2 \
            --sensor-baud 19200 \
            --sensor-timeout 0.5 \
            --sensor-poll-interval 1.0 \
            --sensor-inter-node-delay 0.010 \
            --sensor-reconnect-delay 1.0 \
            --aero-port /dev/ttyAMA4 \
            --aero-address 44 \
            --aero-baud 9600 \
            --aero-timeout 0.5 \
            --aero-poll-interval 2.0 \
            --aero-inter-register-delay 0.050 \
            --aero-reconnect-delay 1.0 \
            --enable-supply-tacho \
            --enable-extract-tacho \
            --tacho-chip /dev/gpiochip0 \
            --supply-tacho-line GPIO17 \
            --extract-tacho-line GPIO27 \
            --tacho-timeout 0.25 \
            --tacho-averaging-periods 6 \
            --log-level INFO \
        >"$TEST_CORE_LOG" 2>&1 &
    TEST_CORE_PID=$!
    wait_test_core
}

start_test_web() {
    env \
        PYTHONPATH="$WT/src" \
        PYTHONUNBUFFERED=1 \
        python3 -m ventilation_core.web.main \
            --host 127.0.0.1 \
            --port "$TEST_WEB_PORT" \
            --socket "$TEST_SOCKET" \
            --telemetry-database "$TEST_HISTORY_DB" \
        >"$TEST_WEB_LOG" 2>&1 &
    TEST_WEB_PID=$!

    local ready=0
    for _ in $(seq 1 20); do
        if kill -0 "$TEST_WEB_PID" 2>/dev/null && \
           curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/health" \
               >/tmp/wvc-history-shadow-web-health.json 2>/dev/null; then
            ready=1
            break
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
echo "HISTORY + SHADOW STAGE 1 — CM5 E2E VALIDATION"
echo "========================================================"

echo
echo "===== 1. PRECHECK ====="
sudo -v

test "$CORE_WAS_ACTIVE" = "active"
test -d "$PROD/.git" -o -f "$PROD/.git"
test -d "$WT/.git" -o -f "$WT/.git"

cd "$WT"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "BŁĄD: worktree ma lokalne tracked zmiany."
    git status --short
    exit 1
fi

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
HEAD="$(git rev-parse HEAD)"
echo "HEAD: $HEAD"

echo
echo "===== 2. TEST SUITE ====="
PYTHONWARNINGS="error::ResourceWarning" PYTHONPATH=src \
    python3 -m unittest discover -s tests

echo
echo "===== 3. PRODUKCJA PRZED PRZEŁĄCZENIEM ====="
prod_ctl status >/tmp/wvc-history-shadow-production-before.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-history-shadow-production-before.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
print('production core STOP / 0 V: PASS')
PY

rm -f \
    "$TEST_SOCKET" \
    "$TEST_AUTOMATION_DB" "$TEST_AUTOMATION_DB-wal" "$TEST_AUTOMATION_DB-shm" \
    "$TEST_ALERTS_DB" "$TEST_ALERTS_DB-wal" "$TEST_ALERTS_DB-shm" \
    "$TEST_HISTORY_DB" "$TEST_HISTORY_DB-wal" "$TEST_HISTORY_DB-shm" \
    "$TEST_CORE_LOG" "$TEST_WEB_LOG"

if [ "$TELEMETRY_WAS_ACTIVE" = "active" ]; then
    sudo systemctl stop "$TELEMETRY_SERVICE"
    TELEMETRY_PAUSED=1
fi
if [ "$WEB_WAS_ACTIVE" = "active" ]; then
    sudo systemctl stop "$WEB_SERVICE"
    WEB_PAUSED=1
fi

prod_ctl stop >/dev/null
sudo systemctl stop "$CORE_SERVICE"
CORE_PAUSED=1
test "$(service_state "$CORE_SERVICE")" != "active"
echo "production services safely paused: PASS"

echo
echo "===== 4. TESTOWY CORE Z PRAWDZIWYM HARDWARE ====="
start_test_core
echo "test core + SENSOR/AERO/TACHO + SHADOW boundary: PASS"

echo
echo "===== 5. KONTEKST HARMONOGRAMU DLA SHADOW ====="
python3 - <<'PY'
import json
from datetime import datetime
from zoneinfo import ZoneInfo
weekday=datetime.now(ZoneInfo('Europe/Warsaw')).isoweekday()
window=[{
    'weekday': weekday,
    'start_local': '00:00',
    'end_local': '23:59',
    'expectation': 'OCCUPIED_EXPECTED',
    'enabled': True,
    'label': 'CM5 HISTORY+SHADOW E2E'
}]
for path in ('/tmp/wvc-history-shadow-zone1.json','/tmp/wvc-history-shadow-zone2.json'):
    json.dump(window, open(path,'w'))
print('weekday:', weekday)
PY

test_ctl schedule-replace --zone zone-1 --file /tmp/wvc-history-shadow-zone1.json >/dev/null
test_ctl schedule-replace --zone zone-2 --file /tmp/wvc-history-shadow-zone2.json >/dev/null
sleep 0.5
test_ctl status >/tmp/wvc-history-shadow-state.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-history-shadow-state.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
sh=s['shadow_automation']
assert sh['enabled'] is True
assert sh['actuation_supported'] is False
assert sh['policy_version'] == 'shadow-policy-v1-2026-08-12'
assert sh['tuning_complete'] is False
assert sh['status'] == 'TUNING_REQUIRED', sh
zones={z['zone']: z for z in sh['zones']}
assert set(zones) == {'zone-1','zone-2'}
for z in zones.values():
    assert z['schedule_expectation'] == 'OCCUPIED_EXPECTED'
    assert z['sensor_usable'] is True
assert zones['zone-1']['proposed_supply_voltage'] is None
assert zones['zone-1']['proposed_extract_voltage'] is None
assert zones['zone-2']['proposed_aero_speed'] is None
print('SHADOW policy classified real sensor data: PASS')
print('SHADOW actuation_supported=false and outputs unchanged: PASS')
PY

echo
echo "===== 6. REALNY CAPTURE TELEMETRII DO OSOBNEJ BAZY ====="
env \
    PYTHONPATH="$WT/src" \
    WVC_AI_BRIDGE_URL= \
    WVC_TELEMETRY_SOURCE_ID=cm5-history-shadow-e2e \
    python3 -m ventilation_core.telemetry.main \
        --socket "$TEST_SOCKET" \
        --database "$TEST_HISTORY_DB" \
        --once \
        --log-level INFO

python3 - "$TEST_HISTORY_DB" <<'PY'
import json, sqlite3, sys
path=sys.argv[1]
con=sqlite3.connect(path)
row=con.execute('SELECT captured_at, metrics_json, synced_at FROM telemetry_samples ORDER BY sequence LIMIT 1').fetchone()
assert row is not None
metrics=json.loads(row[1])
assert row[2] is None
assert metrics['mode'] == 'STOP'
assert float(metrics['setpoints']['supply_voltage']) == 0.0
assert float(metrics['setpoints']['extract_voltage']) == 0.0
assert metrics['hardware_ready'] is True
assert metrics['output_state_known'] is True
assert metrics['sensor_bus']['ready'] is True
assert metrics['aero_bus']['ready'] is True
assert metrics['tacho']['ready'] is True
assert metrics['schedule']['available'] is True
shadow=metrics['shadow_automation']
assert shadow['status'] == 'TUNING_REQUIRED'
assert shadow['actuation_supported'] is False
print('real CoreState persisted to telemetry.sqlite3: PASS')
print('schedule + SHADOW included in persisted snapshot: PASS')
print('local capture works with remote sync disabled: PASS')
PY

echo
echo "===== 7. ROLLUP 1m / 15m NA REALNYM SCHEMACIE SNAPSHOTA ====="
PYTHONPATH="$WT/src" python3 - "$TEST_HISTORY_DB" <<'PY'
from datetime import datetime, timedelta, timezone
import json, sqlite3, sys
from pathlib import Path
from ventilation_core.telemetry.store import TelemetryStore
from ventilation_core.telemetry.history import TelemetryHistoryReader

path=Path(sys.argv[1])
con=sqlite3.connect(path)
metrics=json.loads(con.execute('SELECT metrics_json FROM telemetry_samples ORDER BY sequence LIMIT 1').fetchone()[0])
con.close()

store=TelemetryStore(path)
now=datetime.now(timezone.utc)
base=(now - timedelta(minutes=20)).replace(second=5, microsecond=0)
for offset in (0, 20, 40):
    store.append_snapshot(metrics, captured_at=(base + timedelta(seconds=offset)).isoformat())
created=store.build_rollups(now=now, max_buckets_per_resolution=240)
assert created['1m'] >= 1, created
assert created['15m'] >= 1, created
reader=TelemetryHistoryReader(path)
status=reader.status()
assert status.available is True
assert status.total_samples >= 4
assert status.rollup_1m_samples >= 1
assert status.rollup_15m_samples >= 1
assert reader.query(limit=10, resolution='1m')
assert reader.query(limit=10, resolution='15m')
print('rollup 1m: PASS')
print('rollup 15m: PASS')
print('history reader status/query: PASS')
PY

echo
echo "===== 8. READ-ONLY WEB HISTORY API ====="
start_test_web
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/history/status" \
    >/tmp/wvc-history-shadow-history-status.json
curl -fsS -X POST -H 'Content-Type: application/json' \
    -d '{"resolution":"raw","limit":10}' \
    "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/history/query" \
    >/tmp/wvc-history-shadow-history-raw.json
curl -fsS -X POST -H 'Content-Type: application/json' \
    -d '{"resolution":"1m","limit":10}' \
    "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/history/query" \
    >/tmp/wvc-history-shadow-history-1m.json
curl -fsS -X POST -H 'Content-Type: application/json' \
    -d '{"resolution":"15m","limit":10}' \
    "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/history/query" \
    >/tmp/wvc-history-shadow-history-15m.json

python3 - <<'PY'
import json
status=json.load(open('/tmp/wvc-history-shadow-history-status.json'))
raw=json.load(open('/tmp/wvc-history-shadow-history-raw.json'))
m1=json.load(open('/tmp/wvc-history-shadow-history-1m.json'))
m15=json.load(open('/tmp/wvc-history-shadow-history-15m.json'))
assert status['ok'] is True
assert status['history']['available'] is True
assert status['history']['configured'] is True
assert raw['ok'] is True and raw['resolution'] == 'raw' and raw['count'] >= 1
assert m1['ok'] is True and m1['resolution'] == '1m' and m1['count'] >= 1
assert m15['ok'] is True and m15['resolution'] == '15m' and m15['count'] >= 1
print('Web history status/raw/1m/15m: PASS')
PY

HTTP_CODE="$(curl -sS -o /tmp/wvc-history-shadow-negative.json -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' \
    -d '{"resolution":"raw","limit":2001}' \
    "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/history/query")"
test "$HTTP_CODE" = "400"
echo "bounded history limit rejection: PASS"

echo
echo "===== 9. SHADOW/HISTORY NIE ZMIENIŁY WYJŚĆ ====="
test_ctl status >/tmp/wvc-history-shadow-final-state.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-history-shadow-final-state.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
assert s['shadow_automation']['actuation_supported'] is False
print('test core final STOP / 0 V: PASS')
PY

VALIDATION_PASS=1

echo
echo "===== WALIDACJA FUNKCJONALNA ZAKOŃCZONA ====="
echo "cleanup przywróci teraz produkcyjny core, telemetrię i GUI V2."
