#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-power-scheduler-m5b-validation
STATE_DIR=/var/tmp/wvc-power-scheduler-m5b-validation
STATE_PATH="$STATE_DIR/state.json"
BRANCH=agent/automation-v1-scheduler-assumptions
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${M5B_EXPECTED_BRANCH_SHA:-}"
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
MODE="${1:-}"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

cleanup_worktree() {
    if [ -d "$WT" ]; then
        sudo find "$WT" -type d -name __pycache__ -prune -exec rm -rf {} + >/dev/null 2>&1 || true
    fi
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || sudo rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        sudo rm -rf "$WT" >/dev/null 2>&1 || true
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

require_main() {
    cd "$ROOT"
    [ "$(git branch --show-current)" = "main" ] || fail "production checkout is not main"
    [ -z "$(git status --short)" ] || fail "production main is not clean"
    [ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || fail "local main differs from expected production base"
}

require_services() {
    systemctl is-active --quiet ventilation-core.service || fail "ventilation-core.service is not active"
    systemctl is-active --quiet wvc-host-power.service || fail "wvc-host-power.service is not active"

    local core_pid core_cwd host_pid
    core_pid="$(systemctl show ventilation-core.service -p MainPID --value)"
    host_pid="$(systemctl show wvc-host-power.service -p MainPID --value)"
    [ "$core_pid" != "0" ] || fail "ventilation-core PID is zero"
    [ "$host_pid" != "0" ] || fail "wvc-host-power PID is zero"
    core_cwd="$(readlink -f "/proc/$core_pid/cwd")"
    [ "$core_cwd" = "$ROOT" ] || fail "production core is not running from main: $core_cwd"
}

lab_safe_check() {
    local payload
    payload="$(cd "$ROOT" && PYTHONPATH=src python3 -m ventilation_core.ctl status)" || fail "cannot read production core status"
    printf '%s\n' "$payload" | python3 -c '
import json, sys
response=json.load(sys.stdin)
if response.get("ok") is not True:
    raise SystemExit("core status not ok")
s=response.get("state")
if not isinstance(s, dict):
    raise SystemExit("missing core state")
if s.get("mode") not in {"STOP", "FAULT"}:
    raise SystemExit(f"lab mode must be STOP/FAULT, got {s.get(chr(109)+chr(111)+chr(100)+chr(101))!r}")
sp=s.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"logical EC outputs are not 0 V: {sp!r}")
t=s.get("tacho")
if isinstance(t, dict):
    for channel in ("supply", "extract"):
        c=t.get(channel)
        if isinstance(c, dict) and c.get("rpm") not in {None, 0, 0.0}:
            raise SystemExit(f"{channel} TACHO is non-zero: {c.get(chr(114)+chr(112)+chr(109))!r}")
print("PASS: M5B lab preflight: logical EC=0 V and no non-zero TACHO observed")
' || fail "M5B lab safe-state preflight failed"
}

fetch_pinned() {
    cd "$ROOT"
    git fetch origin main "$BRANCH"
    [ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || fail "origin/main changed"
    local branch_sha
    branch_sha="$(git rev-parse "origin/$BRANCH")"
    [ "$branch_sha" = "$EXPECTED_BRANCH_SHA" ] || fail "branch SHA $branch_sha differs from tested $EXPECTED_BRANCH_SHA"
}

ensure_worktree() {
    if git -C "$ROOT" worktree list --porcelain | grep -Fxq "worktree $WT"; then
        [ "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_BRANCH_SHA" ] || fail "existing M5B worktree has wrong SHA"
        return
    fi
    [ ! -e "$WT" ] || fail "M5B path exists but is not a registered worktree: $WT"
    git -C "$ROOT" worktree add --detach "$WT" "$EXPECTED_BRANCH_SHA"
}

prepare() {
    [ "${M5B_ALLOW_REAL_POWEROFF:-}" = "YES" ] || fail "set M5B_ALLOW_REAL_POWEROFF=YES to acknowledge real CM5 poweroff"
    [ "${M5B_LAB_MODE:-}" = "1" ] || fail "M5B is currently restricted to explicit M5B_LAB_MODE=1"
    [ -n "$EXPECTED_BRANCH_SHA" ] || fail "M5B_EXPECTED_BRANCH_SHA is required"

    echo "===== POWER SCHEDULER M5B PREPARE — REAL POWEROFF ====="
    echo "WARNING: this test will call the real wvc-host-power shutdown path."
    echo "Expected behavior: DFR0473 OFF -> CM5 poweroff -> automatic RTC wake about 5 minutes later."

    require_main
    require_services
    lab_safe_check
    [ -z "$(cat "$WAKEALARM")" ] || fail "RTC wakealarm is already armed: $(cat "$WAKEALARM")"
    [ ! -e "$STATE_PATH" ] || fail "stale M5B state exists: $STATE_PATH; do not overwrite diagnostics"

    fetch_pinned
    cleanup_worktree
    ensure_worktree
    [ -f "$WT/tools/validate_power_scheduler_m5b_cm5.py" ] || fail "M5B validator missing"

    echo "===== CROSSING REAL HOST-POWER BOUNDARY ====="
    echo "The terminal is expected to disconnect. Do NOT manually power CM5 back on; wait for RTC wake."

    set +e
    sudo env \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONPATH="$WT/src" \
        M5B_STATE_PATH="$STATE_PATH" \
        M5B_EXPECTED_BRANCH_SHA="$EXPECTED_BRANCH_SHA" \
        M5B_EXPECTED_MAIN_SHA="$EXPECTED_BASE" \
        /usr/bin/python3 "$WT/tools/validate_power_scheduler_m5b_cm5.py" prepare
    local rc=$?
    set -e

    # On a successful run we never reach here because the CM5 powers off.  If
    # PREPARE returned, restore the 12 V owner and remove any RTC alarm.  Keep
    # state/worktree diagnostics for analysis.
    echo "FAIL: M5B PREPARE returned rc=$rc instead of being terminated by host poweroff" >&2
    sudo sh -c "echo 0 > '$WAKEALARM'" >/dev/null 2>&1 || true
    sudo systemctl restart wvc-host-power.service >/dev/null 2>&1 || true
    exit "${rc:-1}"
}

verify() {
    [ -n "$EXPECTED_BRANCH_SHA" ] || fail "M5B_EXPECTED_BRANCH_SHA is required"

    echo "===== POWER SCHEDULER M5B POST-RTC-WAKE VERIFY ====="
    require_main
    require_services
    [ -f "$STATE_PATH" ] || fail "M5B state missing: $STATE_PATH"

    fetch_pinned
    ensure_worktree

    sudo env \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONPATH="$WT/src" \
        M5B_STATE_PATH="$STATE_PATH" \
        /usr/bin/python3 "$WT/tools/validate_power_scheduler_m5b_cm5.py" verify

    [ -z "$(cat "$WAKEALARM")" ] || fail "RTC wakealarm is not empty after RTC wake"

    local core_pid core_cwd host_pid host_status
    core_pid="$(systemctl show ventilation-core.service -p MainPID --value)"
    core_cwd="$(readlink -f "/proc/$core_pid/cwd")"
    host_pid="$(systemctl show wvc-host-power.service -p MainPID --value)"
    host_status="$(systemctl show wvc-host-power.service -p StatusText --value)"

    [ "$core_cwd" = "$ROOT" ] || fail "core did not return to production main"
    [ "$host_pid" != "0" ] || fail "host-power agent is not running after wake"
    printf '%s' "$host_status" | grep -Fq "12 V domain ON" || fail "host-power agent does not report 12 V domain ON: $host_status"

    echo "PASS: production services recovered after RTC wake"
    echo "core PID:       $core_pid"
    echo "core CWD:       $core_cwd"
    echo "host-power PID: $host_pid"
    echo "host status:    $host_status"
    echo "main HEAD:      $(git -C "$ROOT" rev-parse HEAD)"

    cleanup_worktree
    sudo rm -rf "$STATE_DIR"

    echo "PASS: M5B full RTC -> real host-power -> poweroff -> RTC wake validation complete"
}

case "$MODE" in
    prepare) prepare ;;
    verify) verify ;;
    *) fail "usage: $0 prepare|verify" ;;
esac
