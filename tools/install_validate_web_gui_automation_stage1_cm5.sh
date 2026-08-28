#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-webgui-automation-stage1-validation
BRANCH=agent/web-gui-automation-stage1
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${WEBGUI_AUTOMATION_EXPECTED_BRANCH_SHA:-}"
TEST_ROOT=/var/tmp/wvc-webgui-automation-stage1-validation
FAKE_SOCKET="$TEST_ROOT/fake-core.sock"
COMMAND_LOG="$TEST_ROOT/fake-core-commands.jsonl"
WEB_PORT=18093
WEB_URL="http://127.0.0.1:${WEB_PORT}"
CORE_UNIT=ventilation-core.service
HOST_POWER_UNIT=wvc-host-power.service
RTC_WAKE_PATH=/sys/class/rtc/rtc0/wakealarm
FAKE_PID=""
WEB_PID=""
SUCCESS=0

unit_pid() {
    systemctl show "$1" -p MainPID --value 2>/dev/null || true
}

unit_cwd() {
    local pid="$1"
    readlink -f "/proc/$pid/cwd" 2>/dev/null || true
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

stop_pid() {
    local pid="$1"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" >/dev/null 2>&1 || true
        wait "$pid" 2>/dev/null || true
    fi
}

cleanup() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    stop_pid "$WEB_PID"
    stop_pid "$FAKE_PID"
    rm -f "$FAKE_SOCKET"
    remove_worktree_best_effort
    if [ "$SUCCESS" = "1" ]; then
        rm -rf "$TEST_ROOT"
    else
        echo "WebGUI Automation diagnostic files preserved at: $TEST_ROOT" >&2
    fi
    exit "$rc"
}
trap cleanup EXIT INT TERM

echo "===== WEBGUI AUTOMATION STAGE1 CM5 VALIDATION ====="
cd "$ROOT"

[ -n "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: WEBGUI_AUTOMATION_EXPECTED_BRANCH_SHA must pin the exact CI-tested branch commit" >&2
    exit 1
}
[ "$(git branch --show-current)" = "main" ] || {
    echo "FAIL: production repository is not on main" >&2
    exit 1
}
[ -z "$(git status --short)" ] || {
    echo "FAIL: production main working tree is not clean" >&2
    exit 1
}
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: local main is not expected production SHA $EXPECTED_BASE" >&2
    exit 1
}

systemctl is-active --quiet "$CORE_UNIT" || {
    echo "FAIL: $CORE_UNIT is not active" >&2
    exit 1
}
PROD_CORE_PID_BEFORE="$(unit_pid "$CORE_UNIT")"
[ -n "$PROD_CORE_PID_BEFORE" ] && [ "$PROD_CORE_PID_BEFORE" != "0" ] || {
    echo "FAIL: production core has no MainPID" >&2
    exit 1
}
PROD_CORE_CWD_BEFORE="$(unit_cwd "$PROD_CORE_PID_BEFORE")"
[ "$PROD_CORE_CWD_BEFORE" = "$ROOT" ] || {
    echo "FAIL: production core is not running from $ROOT" >&2
    exit 1
}
BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"
HOST_POWER_STATUS_BEFORE="$(systemctl is-active "$HOST_POWER_UNIT" 2>/dev/null || true)"
HOST_POWER_PID_BEFORE="$(unit_pid "$HOST_POWER_UNIT")"
RTC_WAKE_BEFORE="$(cat "$RTC_WAKE_PATH" 2>/dev/null || true)"

echo "PASS: production core preflight; PID=$PROD_CORE_PID_BEFORE CWD=$PROD_CORE_CWD_BEFORE"
echo "INFO: host-power status=$HOST_POWER_STATUS_BEFORE pid=${HOST_POWER_PID_BEFORE:-0} rtc_wake=${RTC_WAKE_BEFORE:-<empty>}"

echo "===== VERIFY REMOTE PINS ====="
REMOTE_MAIN_SHA="$(git ls-remote --exit-code origin refs/heads/main | awk '{print $1}')"
REMOTE_BRANCH_SHA="$(git ls-remote --exit-code origin "refs/heads/$BRANCH" | awk '{print $1}')"
[ "$REMOTE_MAIN_SHA" = "$EXPECTED_BASE" ] || {
    echo "FAIL: origin/main is $REMOTE_MAIN_SHA, expected $EXPECTED_BASE" >&2
    exit 1
}
[ "$REMOTE_BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: remote GUI branch is $REMOTE_BRANCH_SHA, expected CI-tested $EXPECTED_BRANCH_SHA" >&2
    exit 1
}
git fetch --no-tags origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: fetched origin/main differs from expected production SHA" >&2
    exit 1
}
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: fetched GUI branch SHA $BRANCH_SHA differs from CI-tested $EXPECTED_BRANCH_SHA" >&2
    exit 1
}
echo "PASS: main=$EXPECTED_BASE"
echo "PASS: GUI branch=$BRANCH_SHA"

remove_worktree_best_effort
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
chmod 0700 "$TEST_ROOT"
git worktree add --detach "$WT" "$BRANCH_SHA"

[ -f "$WT/tools/validate_web_gui_automation_stage1_cm5.py" ] || {
    echo "FAIL: Python validator is missing from pinned branch" >&2
    exit 1
}

echo "===== START VALIDATION-ONLY FAKE CORE ====="
/usr/bin/python3 - "$FAKE_SOCKET" "$COMMAND_LOG" >"$TEST_ROOT/fake-core.log" 2>&1 <<'PY' &
import json
import os
from pathlib import Path
import socket
import sys

socket_path = Path(sys.argv[1])
command_log = Path(sys.argv[2])
socket_path.unlink(missing_ok=True)
operator = {"mode": "AUTO"}
revision = 0


def operator_doc():
    return {
        "revision": revision,
        "persistent": False,
        "intent": dict(operator),
    }


def state_doc():
    manual = operator if operator.get("mode") == "MANUAL" else {}
    return {
        "mode": "STOP",
        "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
        "output_state_known": True,
        "shadow_automation": {
            "enabled": True,
            "status": "ACTIVE",
            "policy_version": "validation-fixture",
            "actuation_supported": False,
            "operator_mode": operator["mode"],
            "operator_intent_revision": revision,
            "operator_intent_persistent": False,
            "operator_manual_supply_pct": manual.get("manual_supply_pct"),
            "operator_manual_extract_pct": manual.get("manual_extract_pct"),
            "operator_manual_aero_speed": manual.get("manual_aero_speed"),
            "actuation_readiness": {
                "ready": False,
                "actuation_authorized": False,
                "preconditions_satisfied": False,
                "blockers": ["VALIDATION_FIXTURE_NO_ACTUATION"],
            },
            "zones": [
                {
                    "zone_id": "zone1",
                    "automation_state": "NORMAL",
                    "calendar_mode": "AUTO",
                    "calendar_phase": "ACTIVE",
                    "calendar_profile": "VALIDATION",
                    "air_quality_level": "GOOD",
                    "air_quality_driver": None,
                    "thermal_band": "NORMAL",
                    "final_supply_pct": manual.get("manual_supply_pct", 20.0),
                    "final_extract_pct": manual.get("manual_extract_pct", 20.0),
                    "proposed_aero_speed": manual.get("manual_aero_speed", 0),
                    "proposed_supply_voltage": None,
                    "proposed_extract_voltage": None,
                    "control_reason": "VALIDATION_FIXTURE_SHADOW_ONLY",
                    "sensor_pm2_5_ug_m3": 4.0,
                    "sensor_voc_index": 12.0,
                    "sensor_nox_index": 1.0,
                    "inside_temperature_celsius": 21.0,
                    "outside_temperature_celsius": 17.0,
                    "temperature_delta_celsius": 4.0,
                    "tacho_failure_confirmation_seconds": 4.0,
                    "tacho_supply_required": False,
                    "tacho_extract_required": False,
                    "tacho_supply_status": "NOT_REQUIRED",
                    "tacho_extract_status": "NOT_REQUIRED",
                    "tacho_supply_rpm": 0.0,
                    "tacho_extract_rpm": 0.0,
                    "tacho_fault_pattern": None,
                    "tacho_fallback_applied": False,
                }
            ],
        },
    }


def response_for(request):
    global operator, revision
    command = request.get("command")
    if command == "status":
        return {"ok": True, "state": state_doc()}
    if command == "calendar":
        return {
            "ok": True,
            "calendar": {
                "revision": 1,
                "configuration": {
                    "schema_version": 1,
                    "timezone": "Europe/Warsaw",
                    "profiles": [],
                    "rules": [],
                },
                "resolved": {
                    "available": True,
                    "phase": "ACTIVE",
                    "effective_mode": "AUTO",
                    "effective_profile": "VALIDATION",
                },
            },
        }
    if command == "control-engine-operator":
        return {"ok": True, "control_engine_operator": operator_doc()}
    if command == "control-engine-operator-replace":
        raw = request.get("operator")
        if not isinstance(raw, dict):
            return {"ok": False, "error": "operator must be an object"}
        operator = dict(raw)
        revision += 1
        return {"ok": True, "control_engine_operator": operator_doc()}
    return {"ok": False, "error": f"validation fake core rejects command {command!r}"}


with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(8)
    while True:
        connection, _ = server.accept()
        with connection:
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = connection.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
            try:
                request = json.loads(data.decode("utf-8"))
            except Exception as exc:
                response = {"ok": False, "error": f"invalid request: {exc}"}
            else:
                with command_log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(request, separators=(",", ":")) + "\n")
                    handle.flush()
                response = response_for(request)
            connection.sendall(
                (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
            )
PY
FAKE_PID=$!

for _ in $(seq 1 40); do
    [ -S "$FAKE_SOCKET" ] && break
    if ! kill -0 "$FAKE_PID" 2>/dev/null; then
        echo "FAIL: validation fake core exited" >&2
        cat "$TEST_ROOT/fake-core.log" >&2 || true
        exit 1
    fi
    sleep 0.1
done
[ -S "$FAKE_SOCKET" ] || {
    echo "FAIL: validation fake core socket was not created" >&2
    exit 1
}
echo "PASS: validation-only fake core ready; production core socket is not used by staged WebGUI"

echo "===== START ISOLATED BRANCH WEBGUI ====="
env \
    PYTHONPATH="$WT/src" \
    PYTHONUNBUFFERED=1 \
    WVC_WEB_HOST=127.0.0.1 \
    WVC_WEB_PORT="$WEB_PORT" \
    WVC_CORE_SOCKET="$FAKE_SOCKET" \
    WVC_WEB_CORE_TIMEOUT=2 \
    WVC_WEB_TELEMETRY_DATABASE="$TEST_ROOT/telemetry.sqlite3" \
    WVC_WEB_ALERT_DATABASE="$TEST_ROOT/alerts.sqlite3" \
    WVC_WEB_WEATHER_SNAPSHOT="$TEST_ROOT/weather.json" \
    WVC_WEB_AI_ADVISORY_CACHE="$TEST_ROOT/ai-advisory.json" \
    WVC_HOST_POWER_SOCKET="$TEST_ROOT/host-power-unavailable.sock" \
    /usr/bin/python3 -m ventilation_core.web.main \
    >"$TEST_ROOT/web.log" 2>&1 &
WEB_PID=$!

for _ in $(seq 1 60); do
    if curl --silent --show-error --fail --max-time 2 "$WEB_URL/api/v1/state" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$WEB_PID" 2>/dev/null; then
        echo "FAIL: isolated branch WebGUI exited" >&2
        tail -n 100 "$TEST_ROOT/web.log" >&2 || true
        exit 1
    fi
    sleep 0.15
done
curl --silent --show-error --fail --max-time 2 "$WEB_URL/api/v1/state" >/dev/null || {
    echo "FAIL: isolated branch WebGUI did not become ready on $WEB_URL" >&2
    tail -n 100 "$TEST_ROOT/web.log" >&2 || true
    exit 1
}
echo "PASS: isolated branch WebGUI ready on $WEB_URL (pid=$WEB_PID)"

echo "===== WEBGUI AUTOMATION INTEGRATION ====="
env PYTHONPATH="$WT/src" /usr/bin/python3 \
    "$WT/tools/validate_web_gui_automation_stage1_cm5.py" \
    --web-url "$WEB_URL" \
    --command-log "$COMMAND_LOG"

echo "===== VERIFY PRODUCTION RUNTIME UNTOUCHED ====="
PROD_CORE_PID_AFTER="$(unit_pid "$CORE_UNIT")"
[ "$PROD_CORE_PID_AFTER" = "$PROD_CORE_PID_BEFORE" ] || {
    echo "FAIL: production core PID changed: before=$PROD_CORE_PID_BEFORE after=$PROD_CORE_PID_AFTER" >&2
    exit 1
}
[ "$(unit_cwd "$PROD_CORE_PID_AFTER")" = "$ROOT" ] || {
    echo "FAIL: production core CWD changed" >&2
    exit 1
}
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$BOOT_ID_BEFORE" ] || {
    echo "FAIL: CM5 boot ID changed during validation" >&2
    exit 1
}
HOST_POWER_STATUS_AFTER="$(systemctl is-active "$HOST_POWER_UNIT" 2>/dev/null || true)"
HOST_POWER_PID_AFTER="$(unit_pid "$HOST_POWER_UNIT")"
[ "$HOST_POWER_STATUS_AFTER" = "$HOST_POWER_STATUS_BEFORE" ] || {
    echo "FAIL: host-power service status changed" >&2
    exit 1
}
[ "$HOST_POWER_PID_AFTER" = "$HOST_POWER_PID_BEFORE" ] || {
    echo "FAIL: host-power service PID changed" >&2
    exit 1
}
RTC_WAKE_AFTER="$(cat "$RTC_WAKE_PATH" 2>/dev/null || true)"
[ "$RTC_WAKE_AFTER" = "$RTC_WAKE_BEFORE" ] || {
    echo "FAIL: RTC wakealarm changed during validation" >&2
    exit 1
}
[ "$(git branch --show-current)" = "main" ] || {
    echo "FAIL: production repository branch changed" >&2
    exit 1
}
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || {
    echo "FAIL: production main HEAD changed" >&2
    exit 1
}
[ -z "$(git status --short)" ] || {
    echo "FAIL: production main working tree became dirty" >&2
    exit 1
}

echo "PASS: production ventilation-core PID/CWD unchanged"
echo "PASS: host-power service status/PID unchanged"
echo "PASS: RTC wakealarm unchanged"
echo "PASS: boot ID unchanged"
echo "PASS: production main remains clean at $EXPECTED_BASE"

SUCCESS=1
trap - EXIT INT TERM
stop_pid "$WEB_PID"
WEB_PID=""
stop_pid "$FAKE_PID"
FAKE_PID=""
rm -f "$FAKE_SOCKET"
remove_worktree_best_effort
rm -rf "$TEST_ROOT"

echo "===== RESULT ====="
echo "PASS: WebGUI Automation Stage1 validated on CM5 without access to the production core socket or physical control path"
echo "branch SHA:      $BRANCH_SHA"
echo "production SHA:  $EXPECTED_BASE"
echo "production PID:  $PROD_CORE_PID_BEFORE (unchanged)"
echo "WebGUI test port: $WEB_PORT"
