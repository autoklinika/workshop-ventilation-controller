#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-pr77-runtime-validation
BRANCH=agent/cm5-shutdown-alert-ai-stage1
EXPECTED_BASE=c76dde9aeacbb15625298a4a6d19d3dfeca8cb2f
UNIT=ventilation-core.service
DROPIN_DIR=/etc/systemd/system/${UNIT}.d
DROPIN_PATH=${DROPIN_DIR}/99-zz-pr77-safe-shutdown-validation.conf

unit_pid() {
    systemctl show "$UNIT" -p MainPID --value
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

force_off_best_effort() {
    local src="$1"
    timeout 20s env PYTHONPATH="$src" /usr/bin/python3 -m ventilation_core.ctl stop >/dev/null 2>&1 || true
    timeout 90s env PYTHONPATH="$src" /usr/bin/python3 -m ventilation_core.ctl aero-airing off >/dev/null 2>&1 || true
    sleep 1
    timeout 90s env PYTHONPATH="$src" /usr/bin/python3 -m ventilation_core.ctl aero-speed 0 >/dev/null 2>&1 || true
}

require_safe_state() {
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
    raise SystemExit(f"FAIL: {label}: status request failed")
state = doc.get("state") or {}
sp = state.get("setpoints") or {}
if state.get("mode") != "STOP":
    raise SystemExit(f"FAIL: {label}: mode is not STOP: {state.get('mode')!r}")
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
if state.get("output_state_known") is not True:
    raise SystemExit(f"FAIL: {label}: output_state_known is not true")
aero = state.get("aero_bus") or {}
if not all(aero.get(k) is True for k in ("ready", "worker_alive", "online", "usable")):
    raise SystemExit(f"FAIL: {label}: AERO is not ready/alive/online/usable: {aero!r}")
telemetry = aero.get("telemetry") or {}
if telemetry.get("fan_1_percent") != 0 or telemetry.get("fan_2_percent") != 0:
    raise SystemExit(f"FAIL: {label}: AERO fan power is not 0%: {telemetry!r}")
print(f"PASS: {label}: STOP / 0 V / AERO 0%")
PY
}

remove_worktree_best_effort() {
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}

emergency_rollback() {
    local rc=$?
    trap - EXIT INT TERM
    set +e
    echo "===== PR #77 EMERGENCY ROLLBACK =====" >&2

    if [ -d "$WT/src" ] && systemctl is-active --quiet "$UNIT"; then
        force_off_best_effort "$WT/src"
    fi

    rm -f "$DROPIN_PATH"
    systemctl daemon-reload
    systemctl restart "$UNIT"
    sleep 4

    if systemctl is-active --quiet "$UNIT"; then
        force_off_best_effort "$ROOT/src"
        sleep 3
        local pid
        pid="$(unit_pid)"
        echo "rollback core CWD: $(unit_cwd "$pid" 2>/dev/null || true)" >&2
        require_safe_state "$ROOT/src" "rollback main" >&2 || true
    else
        echo "CRITICAL: ventilation-core is not active after rollback attempt" >&2
    fi

    remove_worktree_best_effort
    exit "$rc"
}
trap emergency_rollback EXIT INT TERM

echo "===== PR #77 RUNTIME ACTIVE -> OFF VALIDATION ====="
cd "$ROOT"

[ "$(id -u)" -eq 0 ] || { echo "FAIL: run with sudo/root" >&2; exit 2; }
[ "$(git branch --show-current)" = "main" ] || { echo "FAIL: production repo is not on main" >&2; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: production main working tree is not clean" >&2; exit 1; }
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || { echo "FAIL: local main is not expected production base" >&2; exit 1; }
[ ! -e "$DROPIN_PATH" ] || { echo "FAIL: PR77 validation drop-in already exists: $DROPIN_PATH" >&2; exit 1; }

systemctl is-active --quiet "$UNIT" || { echo "FAIL: $UNIT is not active" >&2; exit 1; }
MAIN_PID_BEFORE="$(unit_pid)"
[ "$(unit_cwd "$MAIN_PID_BEFORE")" = "$ROOT" ] || { echo "FAIL: production core is not running from main" >&2; exit 1; }

require_safe_state "$ROOT/src" "preflight main"

git fetch origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || { echo "FAIL: origin/main changed" >&2; exit 1; }

remove_worktree_best_effort
git worktree add --detach "$WT" "origin/$BRANCH"

install -d -m 0755 "$DROPIN_DIR"
cat >"$DROPIN_PATH" <<EOF
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
EOF
chmod 0644 "$DROPIN_PATH"

systemctl daemon-reload
systemctl restart "$UNIT"
sleep 4
systemctl is-active --quiet "$UNIT" || { echo "FAIL: branch core did not become active" >&2; exit 1; }

BRANCH_PID="$(unit_pid)"
[ "$BRANCH_PID" != "$MAIN_PID_BEFORE" ] || { echo "FAIL: core PID did not change for branch rollout" >&2; exit 1; }
[ "$(unit_cwd "$BRANCH_PID")" = "$WT" ] || { echo "FAIL: core is not running from PR77 worktree" >&2; exit 1; }
require_safe_state "$WT/src" "PR77 runtime before active test"

echo "===== EXECUTE REAL ACTIVE -> OFF TEST ON PR #77 CORE ====="
env PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_safe_shutdown_active_to_off_cm5.py" \
    --confirm-active-to-off-test

sleep 4
require_safe_state "$WT/src" "PR77 runtime after active-to-off test"

echo "===== RESTORE PRODUCTION MAIN ====="
rm -f "$DROPIN_PATH"
systemctl daemon-reload
systemctl restart "$UNIT"
sleep 4
systemctl is-active --quiet "$UNIT" || { echo "FAIL: production main core did not become active" >&2; exit 1; }

MAIN_PID_AFTER="$(unit_pid)"
[ "$MAIN_PID_AFTER" != "$BRANCH_PID" ] || { echo "FAIL: core PID did not change during rollback to main" >&2; exit 1; }
[ "$(unit_cwd "$MAIN_PID_AFTER")" = "$ROOT" ] || { echo "FAIL: core did not return to production main CWD" >&2; exit 1; }

force_off_best_effort "$ROOT/src"
sleep 4
require_safe_state "$ROOT/src" "final production main"

remove_worktree_best_effort
trap - EXIT INT TERM

echo "PASS: PR #77 branch runtime ACTIVE -> OFF validated and production main restored safely"
echo "main before PID: $MAIN_PID_BEFORE"
echo "branch test PID: $BRANCH_PID"
echo "main after PID:  $MAIN_PID_AFTER"
echo "final CWD: $ROOT"
