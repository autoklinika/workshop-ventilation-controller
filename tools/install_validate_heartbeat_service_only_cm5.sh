#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-heartbeat-service-only-validation
BRANCH=agent/heartbeat-service-only-alert-policy
EXPECTED_BASE=5fb252fdf2405cdcf76a1cc7b62e84140c678309
UNIT=ventilation-core.service
AGENT_UNIT=wvc-service-agent.service
DROPIN_DIR=/etc/systemd/system/${UNIT}.d
DROPIN_PATH=${DROPIN_DIR}/98-heartbeat-service-only-validation.conf
POLICY=/etc/workshop-ventilation/alerts-v2.toml
DEPLOYED=0
ORIGINAL_AGENT_PID=""

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

require_root() {
    [ "$(id -u)" -eq 0 ] || fail "run with sudo/root"
}

unit_pid() {
    systemctl show "$1" -p MainPID --value
}

core_cwd() {
    local pid
    pid="$(unit_pid "$UNIT")"
    [ -n "$pid" ] && [ "$pid" != "0" ] && readlink -f "/proc/$pid/cwd"
}

require_active() {
    systemctl is-active --quiet "$1" || fail "required service inactive: $1"
}

require_main_source_of_truth() {
    [ -d "$ROOT/.git" ] || fail "production repository missing: $ROOT"
    [ "$(sudo -u wentylacja git -C "$ROOT" branch --show-current)" = "main" ] \
        || fail "production repository is not on main"
    [ -z "$(sudo -u wentylacja git -C "$ROOT" status --porcelain)" ] \
        || fail "production main working tree is not clean"
    [ "$(sudo -u wentylacja git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_BASE" ] \
        || fail "local main HEAD differs from validated base $EXPECTED_BASE"
}

fetch_validation_branch() {
    echo "===== FETCH VALIDATION BRANCH ====="
    # Refresh normal remote-tracking refs instead of relying on FETCH_HEAD.
    sudo -u wentylacja git -C "$ROOT" fetch --prune origin

    [ "$(sudo -u wentylacja git -C "$ROOT" rev-parse origin/main)" = "$EXPECTED_BASE" ] \
        || fail "origin/main moved from validated base $EXPECTED_BASE; rebase/review required"
    sudo -u wentylacja git -C "$ROOT" rev-parse --verify "origin/$BRANCH" >/dev/null \
        || fail "validation branch is missing on origin: $BRANCH"

    if [ -e "$WT" ]; then
        sudo -u wentylacja git -C "$ROOT" worktree remove --force "$WT" 2>/dev/null || true
        rm -rf "$WT"
    fi
    sudo -u wentylacja git -C "$ROOT" worktree prune
    sudo -u wentylacja git -C "$ROOT" worktree add --detach "$WT" "origin/$BRANCH"

    echo "main HEAD:       $(sudo -u wentylacja git -C "$ROOT" rev-parse HEAD)"
    echo "validation HEAD: $(sudo -u wentylacja git -C "$WT" rev-parse HEAD)"
    echo "validation diff:"
    sudo -u wentylacja git -C "$ROOT" diff --stat "$EXPECTED_BASE...origin/$BRANCH"
}

preflight() {
    echo "===== PRE-FLIGHT ====="
    require_active "$UNIT"
    require_active "$AGENT_UNIT"
    [ "$(core_cwd)" = "$ROOT" ] \
        || fail "core is not running from production main: $(core_cwd)"
    [ ! -e "$DROPIN_PATH" ] || fail "stale validation drop-in exists: $DROPIN_PATH"
    [ -f "$POLICY" ] || fail "runtime AlertV2 policy missing: $POLICY"

    PYTHONPATH="$WT/src" /usr/bin/python3 -m ventilation_core.alertctl validate "$POLICY"
    PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_alert_v2_stage4a_preflight.py" \
        --samples 5 \
        --interval 0.2
}

write_dropin() {
    install -d -m 0755 "$DROPIN_DIR"
    cat >"$DROPIN_PATH" <<EOF
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
EOF
    chmod 0644 "$DROPIN_PATH"
}

rollback_to_main() {
    echo "===== ROLLBACK TO MAIN ====="
    rm -f "$DROPIN_PATH"
    systemctl daemon-reload
    systemctl restart "$UNIT"
    sleep 2
    require_active "$UNIT"
    require_active "$AGENT_UNIT"

    local cwd
    cwd="$(core_cwd)"
    [ "$cwd" = "$ROOT" ] || fail "rollback core cwd is $cwd, expected $ROOT"

    if [ -n "$ORIGINAL_AGENT_PID" ]; then
        [ "$(unit_pid "$AGENT_UNIT")" = "$ORIGINAL_AGENT_PID" ] \
            || fail "Service Agent PID changed unexpectedly during validation"
    fi

    PYTHONPATH="$ROOT/src" /usr/bin/python3 - <<'PY'
from ventilation_core.alert_v2_stage4b_runtime import CoreReadOnlyClient, require_passive_safe_state
status = CoreReadOnlyClient(timeout_seconds=1.0).request("status")
require_passive_safe_state(status)
print("PASS: main runtime restored in STOP / 0 V / output_state_known")
PY
    DEPLOYED=0
}

emergency_cleanup() {
    local rc=$?
    if [ "$DEPLOYED" -eq 1 ] || [ -e "$DROPIN_PATH" ]; then
        echo "===== EMERGENCY CLEANUP =====" >&2
        rm -f "$DROPIN_PATH" || true
        systemctl daemon-reload || true
        systemctl restart "$UNIT" || true
        sleep 2 || true
        echo "core after cleanup: $(systemctl is-active "$UNIT" 2>/dev/null || true) cwd=$(core_cwd 2>/dev/null || true)" >&2
    fi
    exit "$rc"
}

main() {
    require_root
    require_main_source_of_truth
    fetch_validation_branch
    preflight

    ORIGINAL_AGENT_PID="$(unit_pid "$AGENT_UNIT")"
    local old_core_pid new_core_pid
    old_core_pid="$(unit_pid "$UNIT")"

    trap emergency_cleanup EXIT INT TERM

    echo "===== DEPLOY PR #76 RUNTIME ====="
    write_dropin
    systemctl daemon-reload
    DEPLOYED=1
    systemctl restart "$UNIT"
    sleep 2
    require_active "$UNIT"
    require_active "$AGENT_UNIT"

    new_core_pid="$(unit_pid "$UNIT")"
    [ "$new_core_pid" != "$old_core_pid" ] || fail "core PID did not change on validation deployment"
    [ "$(unit_pid "$AGENT_UNIT")" = "$ORIGINAL_AGENT_PID" ] \
        || fail "Service Agent PID changed during core-only deployment"
    [ "$(core_cwd)" = "$WT" ] || fail "core did not start from validation worktree"

    echo "old core PID: $old_core_pid"
    echo "new core PID: $new_core_pid"
    echo "service-agent PID unchanged: $ORIGINAL_AGENT_PID"
    echo "core cwd: $(core_cwd)"

    echo "===== GENERIC ALERTV2 RUNTIME VALIDATION ====="
    PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_alert_v2_stage5_production_read_only_cm5.py" \
        --policy "$POLICY" \
        --expected-worktree "$WT" \
        --samples 12 \
        --interval 0.25

    echo "===== HEARTBEAT SERVICE-ONLY FAULT VALIDATION ====="
    PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_heartbeat_service_only_cm5.py" \
        --target-node sensor-node-2 \
        --poll-interval 1.0 \
        --offline-timeout 60 \
        --recovery-timeout 35 \
        --settle-timeout 15

    rollback_to_main
    trap - EXIT INT TERM

    echo "===== VALIDATION PASS ====="
    echo "PR #76 behavior validated on physical CM5."
    echo "Production runtime has been restored to main $EXPECTED_BASE."
    echo "NOTE: until PR #76 is explicitly merged/deployed, main may again emit KAMOD_HEARTBEAT_LOST on a future service heartbeat dropout."
}

main "$@"
