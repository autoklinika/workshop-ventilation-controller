#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-power-scheduler-m5a-validation
BRANCH=agent/automation-v1-scheduler-assumptions
EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8
EXPECTED_BRANCH_SHA="${M5A_EXPECTED_BRANCH_SHA:-}"
WAKEALARM=/sys/class/rtc/rtc0/wakealarm

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

cleanup() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    sudo sh -c "echo 0 > '$WAKEALARM'" >/dev/null 2>&1 || true
    cleanup_worktree
    exit "$rc"
}
trap cleanup EXIT INT TERM

cd "$ROOT"

echo "===== POWER SCHEDULER M5A CM5 VALIDATION ====="
[ -n "$EXPECTED_BRANCH_SHA" ] || { echo "FAIL: M5A_EXPECTED_BRANCH_SHA is required" >&2; exit 1; }
[ "$(git branch --show-current)" = "main" ] || { echo "FAIL: production checkout is not main" >&2; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: production main is not clean" >&2; exit 1; }
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || { echo "FAIL: local main differs from expected production base" >&2; exit 1; }

CORE_PID_BEFORE="$(systemctl show ventilation-core.service -p MainPID --value)"
CORE_CWD_BEFORE="$(readlink -f "/proc/$CORE_PID_BEFORE/cwd")"
[ "$CORE_CWD_BEFORE" = "$ROOT" ] || { echo "FAIL: production core is not running from main" >&2; exit 1; }

HOST_POWER_PID_BEFORE="$(systemctl show wvc-host-power.service -p MainPID --value)"
[ "$HOST_POWER_PID_BEFORE" != "0" ] || { echo "FAIL: wvc-host-power.service is not running" >&2; exit 1; }

CURRENT_ALARM="$(cat "$WAKEALARM")"
[ -z "$CURRENT_ALARM" ] || { echo "FAIL: RTC wakealarm already armed: $CURRENT_ALARM" >&2; exit 1; }

echo "===== FETCH PINNED M5A ====="
git fetch origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || { echo "FAIL: origin/main changed" >&2; exit 1; }
BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"
[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ] || {
    echo "FAIL: branch SHA $BRANCH_SHA differs from tested $EXPECTED_BRANCH_SHA" >&2
    exit 1
}

cleanup_worktree
git worktree add --detach "$WT" "$BRANCH_SHA"

[ -f "$WT/tools/validate_power_scheduler_m5a_cm5.py" ] || { echo "FAIL: M5A validator missing" >&2; exit 1; }

echo "===== RUN REAL RTC + NON-ACTUATING HOST-POWER BOUNDARY PROBE ====="
sudo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$WT/src" \
    /usr/bin/python3 "$WT/tools/validate_power_scheduler_m5a_cm5.py"

FINAL_ALARM="$(cat "$WAKEALARM")"
[ -z "$FINAL_ALARM" ] || { echo "FAIL: validator left RTC wakealarm armed: $FINAL_ALARM" >&2; exit 1; }

CORE_PID_AFTER="$(systemctl show ventilation-core.service -p MainPID --value)"
CORE_CWD_AFTER="$(readlink -f "/proc/$CORE_PID_AFTER/cwd")"
HOST_POWER_PID_AFTER="$(systemctl show wvc-host-power.service -p MainPID --value)"

[ "$CORE_PID_AFTER" = "$CORE_PID_BEFORE" ] || { echo "FAIL: ventilation-core PID changed during M5A" >&2; exit 1; }
[ "$CORE_CWD_AFTER" = "$ROOT" ] || { echo "FAIL: ventilation-core CWD changed during M5A" >&2; exit 1; }
[ "$HOST_POWER_PID_AFTER" = "$HOST_POWER_PID_BEFORE" ] || { echo "FAIL: host-power agent PID changed during M5A" >&2; exit 1; }

trap - EXIT INT TERM
cleanup_worktree

echo "PASS: M5A did not restart core, call real host-power, or power off CM5"
echo "branch SHA:      $BRANCH_SHA"
echo "core PID:        $CORE_PID_AFTER"
echo "host-power PID:  $HOST_POWER_PID_AFTER"
