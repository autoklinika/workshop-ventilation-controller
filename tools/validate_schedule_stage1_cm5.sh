#!/usr/bin/env bash
set -Eeuo pipefail

PROD="/home/wentylacja/workshop-ventilation-controller"
WT="/home/wentylacja/workshop-ventilation-history-stage1"
BRANCH="agent/schedules-history-automation-stage1"

CORE_SERVICE="ventilation-core.service"
TELEMETRY_SERVICE="wvc-telemetry-sync.service"
WEB_SERVICE="wvc-web-ui.service"

TEST_SOCKET="/tmp/wvc-schedule-stage1.sock"
TEST_AUTOMATION_DB="/tmp/wvc-schedule-stage1-automation.sqlite3"
TEST_ALERTS_DB="/tmp/wvc-schedule-stage1-alerts.sqlite3"
TEST_HISTORY_DB="/tmp/wvc-schedule-stage1-history.sqlite3"
TEST_CORE_LOG_BASE="/tmp/wvc-schedule-stage1-core"
TEST_WEB_LOG="/tmp/wvc-schedule-stage1-web.log"
TEST_WEB_PORT=18092

TEST_CORE_PID=""
TEST_WEB_PID=""
TEST_CORE_RUN=0
VALIDATION_PASS=0
RESTORE_OK=0

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

TELEMETRY_WAS_ACTIVE="$(service_state "$TELEMETRY_SERVICE")"
WEB_WAS_ACTIVE="$(service_state "$WEB_SERVICE")"
CORE_WAS_ACTIVE="$(service_state "$CORE_SERVICE")"

stop_test_core() {
    if [ -n "${TEST_CORE_PID:-}" ] && kill -0 "$TEST_CORE_PID" 2>/dev/null; then
        test_ctl shutdown >/tmp/wvc-schedule-stage1-shutdown.json 2>/dev/null || true
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

stop_test_web() {
    if [ -n "${TEST_WEB_PID:-}" ] && kill -0 "$TEST_WEB_PID" 2>/dev/null; then
        kill -TERM "$TEST_WEB_PID" 2>/dev/null || true
        wait "$TEST_WEB_PID" 2>/dev/null || true
    fi
    TEST_WEB_PID=""
}

wait_production_core() {
    local ready=0
    for _ in $(seq 1 30); do
        if [ "$(service_state "$CORE_SERVICE")" = "active" ] && \
           prod_ctl status >/tmp/wvc-schedule-stage1-production-restored.json 2>/dev/null; then
            if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-production-restored.json'))['state']
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
    set +e

    stop_test_web
    stop_test_core

    echo
    echo "===== RESTORE PRODUKCJI ====="

    if [ "$CORE_WAS_ACTIVE" = "active" ]; then
        sudo systemctl start "$CORE_SERVICE"
        if wait_production_core; then
            if prod_ctl stop >/tmp/wvc-schedule-stage1-production-stop.json 2>/dev/null; then
                if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-production-stop.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
print('production core: STOP / 0 V / hardware ready: PASS')
PY
                then
                    RESTORE_OK=1
                fi
            fi
        fi
    else
        RESTORE_OK=1
    fi

    if [ "$TELEMETRY_WAS_ACTIVE" = "active" ]; then
        sudo systemctl start "$TELEMETRY_SERVICE" || RESTORE_OK=0
    fi
    if [ "$WEB_WAS_ACTIVE" = "active" ]; then
        sudo systemctl start "$WEB_SERVICE" || RESTORE_OK=0
    fi

    echo "core:      $(service_state "$CORE_SERVICE")"
    echo "telemetry: $(service_state "$TELEMETRY_SERVICE")"
    echo "web V2:    $(service_state "$WEB_SERVICE")"

    if [ "$RESTORE_OK" != "1" ]; then
        echo "BŁĄD KRYTYCZNY: nie udało się jednoznacznie potwierdzić bezpiecznego restore produkcji."
        rc=1
    fi

    if [ "$rc" = "0" ] && [ "$VALIDATION_PASS" = "1" ]; then
        echo
        echo "========================================================"
        echo "SCHEDULE STAGE 1 — CM5 E2E VALIDATION: PASS"
        echo "========================================================"
        echo "produkcyjny core:       PRZYWRÓCONY"
        echo "produkcyjny stan:       STOP / 0 V"
        echo "produkcyjna automation: NIE ZMIENIANA"
        echo "produkcyjna telemetria: PRZYWRÓCONA"
        echo "produkcyjny GUI V2:     PRZYWRÓCONY"
        echo "test DB:                $TEST_AUTOMATION_DB"
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
           test_ctl status >/tmp/wvc-schedule-stage1-test-state.json 2>/dev/null; then
            if python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-test-state.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
assert s['output_state_known'] is True
schedule=s['schedule']
assert schedule is not None
assert schedule['available'] is True
assert schedule['timezone'] == 'Europe/Warsaw'
PY
            then
                ready=1
                break
            fi
        fi
        sleep 1
    done
    if [ "$ready" != "1" ]; then
        echo "BŁĄD: testowy core nie osiągnął bezpiecznego stanu."
        cat "${TEST_CORE_LOG_BASE}-${TEST_CORE_RUN}.log" 2>/dev/null || true
        return 1
    fi
}

wait_test_hardware() {
    local ready=0
    for _ in $(seq 1 30); do
        if test_ctl status >/tmp/wvc-schedule-stage1-test-state.json 2>/dev/null && \
           python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-test-state.json'))['state']

sb=s['sensor_bus']
assert sb is not None and sb['ready'] is True and sb['worker_alive'] is True
nodes={int(n['slave_address']): n for n in sb['nodes']}
assert set(nodes) == {1, 2}
for n in nodes.values():
    assert n['online'] is True and n['usable'] is True

a=s['aero_bus']
assert a is not None and a['ready'] is True and a['worker_alive'] is True
assert a['online'] is True and a['usable'] is True

t=s['tacho']
assert t is not None and t['ready'] is True and t['worker_alive'] is True
PY
        then
            ready=1
            break
        fi
        sleep 1
    done
    if [ "$ready" != "1" ]; then
        echo "BŁĄD: testowy core nie potwierdził wszystkich monitorów hardware."
        test_ctl status || true
        return 1
    fi
}

start_test_core() {
    TEST_CORE_RUN=$((TEST_CORE_RUN + 1))
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
        >"${TEST_CORE_LOG_BASE}-${TEST_CORE_RUN}.log" 2>&1 &

    TEST_CORE_PID=$!
    wait_test_core
    wait_test_hardware
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
               >/tmp/wvc-schedule-stage1-web-health.json 2>/dev/null; then
            if python3 - <<'PY'
import json
p=json.load(open('/tmp/wvc-schedule-stage1-web-health.json'))
assert p['ok'] is True
assert p['web'] == 'ok'
assert p['core_available'] is True
PY
            then
                ready=1
                break
            fi
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
echo "SCHEDULE STAGE 1 — CM5 E2E VALIDATION"
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
prod_ctl status >/tmp/wvc-schedule-stage1-production-before.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-production-before.json'))['state']
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
    "$TEST_CORE_LOG_BASE"-*.log "$TEST_WEB_LOG"

if [ "$TELEMETRY_WAS_ACTIVE" = "active" ]; then
    sudo systemctl stop "$TELEMETRY_SERVICE"
fi
if [ "$WEB_WAS_ACTIVE" = "active" ]; then
    sudo systemctl stop "$WEB_SERVICE"
fi

prod_ctl stop >/tmp/wvc-schedule-stage1-production-final-stop.json
sudo systemctl stop "$CORE_SERVICE"
test "$(service_state "$CORE_SERVICE")" != "active"

echo "production services safely paused: PASS"

echo
echo "===== 4. TESTOWY CORE Z PRAWDZIWYM HARDWARE ====="
start_test_core

echo "test core run #1 + SENSOR/AERO/TACHO: PASS"

echo
echo "===== 5. TESTOWY WEB GUI / USTAWIENIA ====="
start_test_web

curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/settings" \
    >/tmp/wvc-schedule-stage1-settings.html
grep -q "Harmonogram pracy stref" /tmp/wvc-schedule-stage1-settings.html
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/schedule.js" \
    >/tmp/wvc-schedule-stage1-schedule.js
grep -q "/api/v1/schedule/zone" /tmp/wvc-schedule-stage1-schedule.js

echo "GUI settings route + schedule editor assets: PASS"

echo
echo "===== 6. ZAPIS OBU STREF PRZEZ WEB API ====="

python3 - <<'PY'
import json
from datetime import datetime
from zoneinfo import ZoneInfo

weekday=datetime.now(ZoneInfo('Europe/Warsaw')).isoweekday()
for zone, label, path in (
    ('zone-1', 'CM5 E2E Strefa 1', '/tmp/wvc-schedule-stage1-zone1.json'),
    ('zone-2', 'CM5 E2E Strefa 2', '/tmp/wvc-schedule-stage1-zone2.json'),
):
    payload={
        'zone': zone,
        'windows': [{
            'weekday': weekday,
            'start_local': '00:00',
            'end_local': '23:59',
            'expectation': 'OCCUPIED_EXPECTED',
            'enabled': True,
            'label': label,
        }],
    }
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False)
print('weekday:', weekday)
PY

for zone in 1 2; do
    code="$(curl -sS -o "/tmp/wvc-schedule-stage1-zone${zone}-ack.json" -w '%{http_code}' \
        -H 'Content-Type: application/json' \
        --data-binary "@/tmp/wvc-schedule-stage1-zone${zone}.json" \
        "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/schedule/zone")"
    test "$code" = "200"
done

curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/schedule" \
    >/tmp/wvc-schedule-stage1-schedule-after-write.json
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/state" \
    >/tmp/wvc-schedule-stage1-state-after-write.json

python3 - <<'PY'
import json

schedule=json.load(open('/tmp/wvc-schedule-stage1-schedule-after-write.json'))['schedule']
assert schedule['available'] is True
assert schedule['timezone'] == 'Europe/Warsaw'
assert len(schedule['windows']) == 2
by_zone={w['zone']: w for w in schedule['windows']}
assert set(by_zone) == {'zone-1', 'zone-2'}
assert by_zone['zone-1']['label'] == 'CM5 E2E Strefa 1'
assert by_zone['zone-2']['label'] == 'CM5 E2E Strefa 2'

states={z['zone']: z for z in schedule['state']['zones']}
assert states['zone-1']['expectation'] == 'OCCUPIED_EXPECTED'
assert states['zone-2']['expectation'] == 'OCCUPIED_EXPECTED'

state=json.load(open('/tmp/wvc-schedule-stage1-state-after-write.json'))['state']
assert state['mode'] == 'STOP'
assert float(state['setpoints']['supply_voltage']) == 0.0
assert float(state['setpoints']['extract_voltage']) == 0.0
assert state['schedule']['available'] is True
print('GUI -> Web API -> core schedule state: PASS')
print('schedule did not actuate DAC: PASS')
PY

python3 - "$TEST_AUTOMATION_DB" <<'PY'
import sqlite3, sys
from contextlib import closing

with closing(sqlite3.connect(sys.argv[1])) as con:
    rows=con.execute(
        'SELECT zone, weekday, start_minute, end_minute, expectation, enabled, label '
        'FROM schedule_windows ORDER BY zone'
    ).fetchall()

assert len(rows) == 2, rows
assert rows[0][0] == 'zone-1' and rows[1][0] == 'zone-2'
assert all(row[2] == 0 and row[3] == 1439 for row in rows)
assert all(row[4] == 'OCCUPIED_EXPECTED' and row[5] == 1 for row in rows)
print('automation.sqlite3 physical persistence: PASS')
PY

echo
echo "===== 7. NEGATYWNY TEST GRANICY GUI ====="

code="$(curl -sS -o /tmp/wvc-schedule-stage1-rejected.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data-binary '{"zone":"zone-1","windows":[{"weekday":1,"start_local":"07:00","end_local":"08:00","command":"set"}]}' \
    "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/schedule/zone")"
test "$code" = "400"

test_ctl status >/tmp/wvc-schedule-stage1-after-reject.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-after-reject.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
print('arbitrary command rejected before core actuation: PASS')
PY

echo
echo "===== 8. RESTART TESTOWEGO CORE — PERSISTENCJA ====="
stop_test_core
start_test_core

echo "test core run #2: PASS"

curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/v1/schedule" \
    >/tmp/wvc-schedule-stage1-schedule-after-restart.json

python3 - <<'PY'
import json
p=json.load(open('/tmp/wvc-schedule-stage1-schedule-after-restart.json'))
s=p['schedule']
assert s['available'] is True
assert len(s['windows']) == 2
labels={w['zone']: w['label'] for w in s['windows']}
assert labels == {
    'zone-1': 'CM5 E2E Strefa 1',
    'zone-2': 'CM5 E2E Strefa 2',
}
states={z['zone']: z['expectation'] for z in s['state']['zones']}
assert states['zone-1'] == 'OCCUPIED_EXPECTED'
assert states['zone-2'] == 'OCCUPIED_EXPECTED'
print('schedule survived core restart: PASS')
PY

test_ctl status >/tmp/wvc-schedule-stage1-final-test-state.json
python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-schedule-stage1-final-test-state.json'))['state']
assert s['mode'] == 'STOP'
assert float(s['setpoints']['supply_voltage']) == 0.0
assert float(s['setpoints']['extract_voltage']) == 0.0
assert s['hardware_ready'] is True
print('test core final STOP / 0 V: PASS')
PY

VALIDATION_PASS=1

echo
echo "===== WALIDACJA FUNKCJONALNA ZAKOŃCZONA ====="
echo "cleanup przywróci teraz produkcyjny core, telemetrię i GUI V2."
