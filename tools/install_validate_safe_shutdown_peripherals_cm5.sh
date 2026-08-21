#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-safe-shutdown-validation
BRANCH=agent/cm5-shutdown-alert-ai-stage1
EXPECTED_BASE=c76dde9aeacbb15625298a4a6d19d3dfeca8cb2f
CORE_UNIT=ventilation-core.service
POWER_UNIT=wvc-host-power.service

cleanup() {
    set +e
    if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
    elif [ -d "$WT" ]; then
        rm -rf "$WT"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

unit_pid() {
    systemctl show "$1" -p MainPID --value
}

unit_cwd() {
    local pid="$1"
    readlink -f "/proc/$pid/cwd"
}

echo "===== SAFE SHUTDOWN PERIPHERAL VALIDATION ====="
cd "$ROOT"

[ "$(git branch --show-current)" = "main" ] || fail "production repo is not on main"
[ -z "$(git status --short)" ] || fail "production main working tree is not clean"
[ "$(git rev-parse HEAD)" = "$EXPECTED_BASE" ] || fail "local main is not expected production base"

git fetch origin main "$BRANCH"
[ "$(git rev-parse origin/main)" = "$EXPECTED_BASE" ] || fail "origin/main changed; review before validation"

git show-ref --verify --quiet "refs/remotes/origin/$BRANCH" || fail "validation branch missing"

systemctl is-active --quiet "$CORE_UNIT" || fail "$CORE_UNIT is not active"
systemctl is-active --quiet "$POWER_UNIT" || fail "$POWER_UNIT is not active"
CORE_PID_BEFORE="$(unit_pid "$CORE_UNIT")"
POWER_PID_BEFORE="$(unit_pid "$POWER_UNIT")"
[[ "$CORE_PID_BEFORE" =~ ^[1-9][0-9]*$ ]] || fail "invalid core PID"
[[ "$POWER_PID_BEFORE" =~ ^[1-9][0-9]*$ ]] || fail "invalid host-power PID"
[ "$(unit_cwd "$CORE_PID_BEFORE")" = "$ROOT" ] || fail "production core is not running from main"

cleanup

git worktree add --detach "$WT" "origin/$BRANCH"

PYTHONPATH="$WT/src" python3 "$WT/tools/validate_safe_shutdown_peripherals_cm5.py" \
    --confirm-active-output-test

CORE_PID_AFTER="$(unit_pid "$CORE_UNIT")"
POWER_PID_AFTER="$(unit_pid "$POWER_UNIT")"
[ "$CORE_PID_AFTER" = "$CORE_PID_BEFORE" ] || fail "core PID changed during validation"
[ "$POWER_PID_AFTER" = "$POWER_PID_BEFORE" ] || fail "host-power PID changed during validation"
[ "$(unit_cwd "$CORE_PID_AFTER")" = "$ROOT" ] || fail "core CWD changed during validation"

FINAL_JSON="$(PYTHONPATH="$ROOT/src" python3 -m ventilation_core.ctl status)"
python3 - "$FINAL_JSON" <<'PY'
import json
import sys

doc = json.loads(sys.argv[1])
if doc.get("ok") is not True:
    raise SystemExit("FAIL: final status request failed")
state = doc.get("state") or {}
setpoints = state.get("setpoints") or {}
if state.get("mode") != "STOP":
    raise SystemExit("FAIL: final mode is not STOP")
if setpoints.get("supply_voltage") != 0.0 or setpoints.get("extract_voltage") != 0.0:
    raise SystemExit("FAIL: final EC fan outputs are not 0 V")
if state.get("output_state_known") is not True:
    raise SystemExit("FAIL: final fan output state is not confirmed")
aero = state.get("aero_bus") or {}
result = aero.get("last_control_result") or {}
if result.get("kind") != "speed" or result.get("target_value") != 0 or result.get("state") != "succeeded":
    raise SystemExit(f"FAIL: final AERO speed 0 confirmation is invalid: {result!r}")
print("final runtime state: STOP / 0 V / AERO speed 0 confirmed")
PY

echo "PASS: PR #77 peripheral shutdown sequence validated on real CM5 hardware without host poweroff"
echo "NOTE: peripherals intentionally remain OFF after this validation"
