#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-alert-v2-stage4
UNIT=ventilation-core.service
AGENT_UNIT=wvc-service-agent.service
POLICY_DIR=/etc/workshop-ventilation
POLICY_PATH=${POLICY_DIR}/alerts-v2.toml
DROPIN_DIR=/etc/systemd/system/${UNIT}.d
DROPIN_PATH=${DROPIN_DIR}/97-alert-v2-stage5-read-only.conf

usage() {
    cat <<'EOF'
Usage:
  sudo tools/deploy_alert_v2_stage5_read_only_cm5.sh apply
  sudo tools/deploy_alert_v2_stage5_read_only_cm5.sh rollback
  sudo tools/deploy_alert_v2_stage5_read_only_cm5.sh status

Stage 5 is control-read-only: it deploys the AlertV2 branch as the production
core runtime and validates that TOML reactions are still NOT executed.
EOF
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "FAIL: run this script with sudo/root" >&2
        exit 2
    fi
}

require_paths() {
    test -d "$ROOT/.git" || { echo "FAIL: production repository missing: $ROOT" >&2; exit 1; }
    test -e "$WT/.git" || { echo "FAIL: Stage 5 worktree missing: $WT" >&2; exit 1; }
    test -f "$WT/config/alerts-v2.default.toml" || { echo "FAIL: AlertV2 default policy missing in worktree" >&2; exit 1; }
    test -f "$WT/tools/validate_alert_v2_stage4a_preflight.py" || { echo "FAIL: Stage 4A preflight tool missing" >&2; exit 1; }
    test -f "$WT/tools/validate_alert_v2_stage5_production_read_only_cm5.py" || { echo "FAIL: Stage 5 validator missing" >&2; exit 1; }
}

unit_pid() {
    systemctl show "$1" -p MainPID --value
}

require_active() {
    systemctl is-active --quiet "$1" || { echo "FAIL: required service is not active: $1" >&2; exit 1; }
}

validate_runtime_policy() {
    PYTHONPATH="$WT/src" /usr/bin/python3 -m ventilation_core.alertctl validate "$POLICY_PATH"
}

preflight() {
    echo "===== STAGE 5 PRE-FLIGHT ====="
    require_active "$UNIT"
    require_active "$AGENT_UNIT"
    PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_alert_v2_stage4a_preflight.py" \
        --samples 5 \
        --interval 0.2
}

install_policy_if_needed() {
    install -d -m 0755 "$POLICY_DIR"
    if [ ! -e "$POLICY_PATH" ]; then
        install -m 0644 "$WT/config/alerts-v2.default.toml" "$POLICY_PATH"
        echo "INFO: installed initial runtime policy: $POLICY_PATH"
    else
        echo "INFO: existing runtime policy preserved: $POLICY_PATH"
    fi
    validate_runtime_policy
}

write_dropin() {
    if [ -e "$DROPIN_PATH" ]; then
        echo "FAIL: Stage 5 drop-in already exists: $DROPIN_PATH" >&2
        echo "Use '$0 status' or '$0 rollback'." >&2
        exit 1
    fi
    install -d -m 0755 "$DROPIN_DIR"
    cat >"$DROPIN_PATH" <<EOF
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
EOF
    chmod 0644 "$DROPIN_PATH"
}

remove_dropin() {
    rm -f "$DROPIN_PATH"
}

validate_after_restart() {
    PYTHONPATH="$WT/src" /usr/bin/python3 "$WT/tools/validate_alert_v2_stage5_production_read_only_cm5.py" \
        --policy "$POLICY_PATH" \
        --expected-worktree "$WT" \
        --samples 30 \
        --interval 0.25
}

restore_legacy_runtime() {
    echo "===== STAGE 5 AUTOMATIC ROLLBACK =====" >&2
    remove_dropin
    systemctl daemon-reload
    systemctl restart "$UNIT"
    sleep 2
    if ! systemctl is-active --quiet "$UNIT"; then
        echo "CRITICAL: legacy production core did not become active after rollback" >&2
        return 1
    fi
    echo "INFO: production core rolled back to base service configuration" >&2
}

apply_rollout() {
    require_paths
    if [ -e "$DROPIN_PATH" ]; then
        echo "FAIL: Stage 5 already appears installed: $DROPIN_PATH" >&2
        exit 1
    fi

    preflight
    install_policy_if_needed

    local old_core_pid old_agent_pid new_core_pid new_agent_pid
    old_core_pid="$(unit_pid "$UNIT")"
    old_agent_pid="$(unit_pid "$AGENT_UNIT")"

    echo "===== INSTALL STAGE 5 DROP-IN ====="
    write_dropin
    systemctl daemon-reload

    echo "===== RESTART PRODUCTION CORE INTO ALERT V2 READ-ONLY RUNTIME ====="
    if ! systemctl restart "$UNIT"; then
        restore_legacy_runtime || true
        echo "FAIL: production core restart failed; rollback attempted" >&2
        exit 1
    fi
    sleep 2

    if ! systemctl is-active --quiet "$UNIT"; then
        restore_legacy_runtime || true
        echo "FAIL: production core is not active after Stage 5 restart; rollback attempted" >&2
        exit 1
    fi
    if ! systemctl is-active --quiet "$AGENT_UNIT"; then
        restore_legacy_runtime || true
        echo "FAIL: Service Agent is not active after Stage 5 restart; rollback attempted" >&2
        exit 1
    fi

    new_core_pid="$(unit_pid "$UNIT")"
    new_agent_pid="$(unit_pid "$AGENT_UNIT")"
    if [ "$new_agent_pid" != "$old_agent_pid" ]; then
        restore_legacy_runtime || true
        echo "FAIL: Service Agent PID changed unexpectedly: $old_agent_pid -> $new_agent_pid" >&2
        exit 1
    fi
    if [ "$new_core_pid" = "$old_core_pid" ]; then
        restore_legacy_runtime || true
        echo "FAIL: production core PID did not change during intentional rollout restart" >&2
        exit 1
    fi

    echo "===== VALIDATE STAGE 5 ====="
    if ! validate_after_restart; then
        restore_legacy_runtime || true
        echo "FAIL: Stage 5 validation failed; production core rolled back" >&2
        exit 1
    fi

    echo "===== STAGE 5 ROLLOUT PASS ====="
    echo "old core PID: $old_core_pid"
    echo "new core PID: $new_core_pid"
    echo "Service Agent PID unchanged: $new_agent_pid"
    echo "runtime worktree: $WT"
    echo "runtime policy: $POLICY_PATH"
    echo "drop-in: $DROPIN_PATH"
    echo "control policy execution: DISABLED"
}

rollback_rollout() {
    require_paths
    if [ ! -e "$DROPIN_PATH" ]; then
        echo "INFO: Stage 5 drop-in is not installed; nothing to rollback"
        exit 0
    fi

    echo "===== STAGE 5 ROLLBACK PRE-FLIGHT ====="
    PYTHONPATH="$WT/src" /usr/bin/python3 - <<'PY'
from ventilation_core.alert_v2_stage4b_runtime import CoreReadOnlyClient, require_passive_safe_state
require_passive_safe_state(CoreReadOnlyClient(timeout_seconds=1.0).request("status"))
print("PASS: production is STOP / 0 V / output_state_known before rollback")
PY

    local old_pid
    old_pid="$(unit_pid "$UNIT")"
    remove_dropin
    systemctl daemon-reload
    systemctl restart "$UNIT"
    sleep 2
    require_active "$UNIT"
    require_active "$AGENT_UNIT"
    local new_pid
    new_pid="$(unit_pid "$UNIT")"
    if [ "$new_pid" = "$old_pid" ]; then
        echo "FAIL: core PID did not change during rollback restart" >&2
        exit 1
    fi

    PYTHONPATH="$WT/src" /usr/bin/python3 - <<'PY'
from ventilation_core.alert_v2_stage4b_runtime import CoreReadOnlyClient, require_passive_safe_state
require_passive_safe_state(CoreReadOnlyClient(timeout_seconds=1.0).request("status"))
print("PASS: base production core is STOP / 0 V / output_state_known after rollback")
PY

    echo "PASS: Stage 5 drop-in removed and production core returned to base runtime"
    echo "NOTE: $POLICY_PATH was intentionally preserved for future validated use"
}

status_rollout() {
    require_paths
    echo "===== STAGE 5 STATUS ====="
    echo "core: $(systemctl is-active "$UNIT" || true) pid=$(unit_pid "$UNIT" || true)"
    echo "service-agent: $(systemctl is-active "$AGENT_UNIT" || true) pid=$(unit_pid "$AGENT_UNIT" || true)"
    if [ -e "$DROPIN_PATH" ]; then
        echo "drop-in: INSTALLED ($DROPIN_PATH)"
        cat "$DROPIN_PATH"
    else
        echo "drop-in: NOT INSTALLED"
    fi
    if [ -e "$POLICY_PATH" ]; then
        echo "policy: PRESENT ($POLICY_PATH)"
        validate_runtime_policy || true
    else
        echo "policy: MISSING ($POLICY_PATH)"
    fi
    local pid
    pid="$(unit_pid "$UNIT" || true)"
    if [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ -e "/proc/$pid/cwd" ]; then
        echo "core cwd: $(readlink -f "/proc/$pid/cwd" || true)"
    fi
}

main() {
    require_root
    case "${1:-}" in
        apply) apply_rollout ;;
        rollback) rollback_rollout ;;
        status) status_rollout ;;
        *) usage; exit 2 ;;
    esac
}

main "$@"
