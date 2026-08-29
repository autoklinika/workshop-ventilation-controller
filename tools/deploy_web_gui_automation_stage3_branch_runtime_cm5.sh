#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wentylacja/workshop-ventilation-controller
WT=/home/wentylacja/wvc-webgui-automation-stage3-runtime
BRANCH=agent/web-gui-automation-stage3-deployment
RUNTIME_SHA=7d29c09a842a2888294a57d1611ea1f0609f4a39
EXPECTED_MAIN=7628c407cfc9c0ea72d262566759ea2d4598fec8
CORE_UNIT=ventilation-core.service
WEB_UNIT=wvc-web-ui.service
CORE_DROPIN_DIR=/etc/systemd/system/${CORE_UNIT}.d
CORE_DROPIN=${CORE_DROPIN_DIR}/90-webgui-automation-stage3-branch-runtime.conf
WEB_DROPIN_DIR=/etc/systemd/system/${WEB_UNIT}.d
WEB_DROPIN=${WEB_DROPIN_DIR}/90-webgui-automation-stage3-branch-runtime.conf
WEB_URL=http://127.0.0.1:18091
WAKEALARM=/sys/class/rtc/rtc0/wakealarm
AUTOMATION_DB=/var/lib/workshop-ventilation/automation.sqlite3
BACKUP_DIR=/var/lib/workshop-ventilation/stage3-branch-runtime-backups

fail() {
    echo "FAIL: $*" >&2
    return 1
}

unit_pid() {
    systemctl show "$1" -p MainPID --value
}

unit_cwd() {
    local pid="$1"
    readlink -f "/proc/$pid/cwd"
}

proc_env_var() {
    local pid="$1"
    local key="$2"
    /usr/bin/python3 - "$pid" "$key" <<'PY'
import sys
from pathlib import Path
pid, key = sys.argv[1], sys.argv[2]
try:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
except OSError:
    print("__UNAVAILABLE__")
    raise SystemExit(0)
prefix = (key + "=").encode()
for entry in raw.split(b"\0"):
    if entry.startswith(prefix):
        print(entry[len(prefix):].decode("utf-8", "replace"))
        break
else:
    print("__UNSET__")
PY
}

read_wakealarm() {
    sudo cat "$WAKEALARM" 2>/dev/null | tr -d '\r\n'
}

ctl_status() {
    local src="$1"
    env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$src" /usr/bin/python3 -B -m ventilation_core.ctl status
}

require_zero_and_shadow() {
    local src="$1"
    local label="$2"
    local require_shadow="${3:-0}"
    local raw
    raw="$(ctl_status "$src")"
    /usr/bin/python3 - "$label" "$require_shadow" "$raw" <<'PY'
import json
import sys
label = sys.argv[1]
require_shadow = sys.argv[2] == "1"
doc = json.loads(sys.argv[3])
if doc.get("ok") is not True:
    raise SystemExit(f"FAIL: {label}: core status rejected")
state = doc.get("state") or {}
sp = state.get("setpoints") or {}
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"FAIL: {label}: EC outputs are not 0 V: {sp!r}")
for channel in ("supply", "extract"):
    row = (state.get("tacho") or {}).get(channel) or {}
    if float(row.get("rpm") or 0.0) != 0.0:
        raise SystemExit(f"FAIL: {label}: {channel} TACHO reports motion: {row!r}")
aero = state.get("aero_bus") or {}
telemetry = aero.get("telemetry") if isinstance(aero, dict) else None
if isinstance(telemetry, dict):
    for key in ("fan_1_percent", "fan_2_percent"):
        value = telemetry.get(key)
        if value not in (None, 0):
            raise SystemExit(f"FAIL: {label}: AERO {key} reports motion: {telemetry!r}")
if require_shadow:
    shadow = state.get("shadow_automation") or {}
    if shadow.get("actuation_supported") is not False:
        raise SystemExit(f"FAIL: {label}: actuation_supported is not false")
    readiness = shadow.get("actuation_readiness") or {}
    if readiness.get("actuation_authorized") is not False:
        raise SystemExit(f"FAIL: {label}: actuation_authorized is not false")
    if readiness.get("ready") is not False:
        raise SystemExit(f"FAIL: {label}: readiness is not false")
print(f"PASS: {label}: EC=0 V / no observed fan motion" + (" / SHADOW non-actuating" if require_shadow else ""))
PY
}

wait_unit_active() {
    local unit="$1"
    local attempt
    for attempt in $(seq 1 80); do
        if systemctl is-active --quiet "$unit"; then
            local pid
            pid="$(unit_pid "$unit")"
            if [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ -d "/proc/$pid" ]; then
                return 0
            fi
        fi
        sleep 0.25
    done
    sudo systemctl status "$unit" --no-pager -l >&2 || true
    sudo journalctl -u "$unit" --no-pager -n 120 >&2 || true
    fail "$unit did not become active"
}

wait_web() {
    local attempt
    for attempt in $(seq 1 80); do
        if curl --silent --show-error --fail --max-time 2 "$WEB_URL/automation" >/dev/null 2>&1 && \
           curl --silent --show-error --fail --max-time 2 "$WEB_URL/api/v1/state" >/dev/null 2>&1; then
            return 0
        fi
        if ! systemctl is-active --quiet "$WEB_UNIT"; then
            sudo systemctl status "$WEB_UNIT" --no-pager -l >&2 || true
            sudo journalctl -u "$WEB_UNIT" --no-pager -n 120 >&2 || true
            fail "$WEB_UNIT exited while waiting for WebGUI"
        fi
        sleep 0.25
    done
    sudo systemctl status "$WEB_UNIT" --no-pager -l >&2 || true
    sudo journalctl -u "$WEB_UNIT" --no-pager -n 120 >&2 || true
    fail "WebGUI did not become ready at $WEB_URL"
}

assert_runtime_unit() {
    local unit="$1"
    local label="$2"
    local pid cwd pythonpath
    wait_unit_active "$unit"
    pid="$(unit_pid "$unit")"
    cwd="$(unit_cwd "$pid")"
    pythonpath="$(proc_env_var "$pid" PYTHONPATH)"
    [ "$cwd" = "$WT" ] || fail "$label CWD=$cwd expected=$WT"
    [ "$pythonpath" = "$WT/src" ] || fail "$label PYTHONPATH=$pythonpath expected=$WT/src"
    echo "PASS: $label runs from Stage3 runtime worktree (pid=$pid)"
}

assert_main_unit() {
    local unit="$1"
    local label="$2"
    local pid cwd
    wait_unit_active "$unit"
    pid="$(unit_pid "$unit")"
    cwd="$(unit_cwd "$pid")"
    [ "$cwd" = "$ROOT" ] || fail "$label CWD=$cwd expected=$ROOT"
    echo "PASS: $label restored to production main (pid=$pid)"
}

prepare_worktree() {
    git -C "$ROOT" fetch --no-tags origin main "$BRANCH"
    [ "$(git -C "$ROOT" rev-parse origin/main)" = "$EXPECTED_MAIN" ] || fail "origin/main moved from validated production SHA"
    git -C "$ROOT" merge-base --is-ancestor "$RUNTIME_SHA" "origin/$BRANCH" || fail "validated runtime SHA is not on $BRANCH"

    if git -C "$ROOT" worktree list --porcelain | grep -Fxq "worktree $WT"; then
        [ "$(git -C "$WT" rev-parse HEAD)" = "$RUNTIME_SHA" ] || fail "existing runtime worktree is not pinned to $RUNTIME_SHA"
        [ -z "$(git -C "$WT" status --short)" ] || fail "runtime worktree is dirty"
    else
        [ ! -e "$WT" ] || fail "$WT exists but is not a registered git worktree"
        git -C "$ROOT" worktree add --detach "$WT" "$RUNTIME_SHA"
    fi
}

backup_automation_db() {
    [ -e "$AUTOMATION_DB" ] || return 0
    local stamp target
    stamp="$(date +%Y%m%d-%H%M%S)"
    target="$BACKUP_DIR/automation-before-stage3-$stamp.sqlite3"
    sudo install -d -m 0770 -o wentylacja -g wentylacja "$BACKUP_DIR"
    /usr/bin/python3 - "$AUTOMATION_DB" "$target" <<'PY'
import sqlite3
import sys
src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=5.0)
target = sqlite3.connect(dst, timeout=5.0)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
print(dst)
PY
    chmod 0660 "$target"
    echo "PASS: automation DB safety backup created: $target"
}

write_dropins() {
    sudo install -d -m 0755 "$CORE_DROPIN_DIR" "$WEB_DROPIN_DIR"
    cat <<EOF | sudo tee "$CORE_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
EOF
    cat <<EOF | sudo tee "$WEB_DROPIN" >/dev/null
[Service]
WorkingDirectory=$WT
Environment=PYTHONPATH=$WT/src
Environment=PYTHONDONTWRITEBYTECODE=1
EOF
    sudo chmod 0644 "$CORE_DROPIN" "$WEB_DROPIN"
    sudo systemctl daemon-reload
}

remove_dropins() {
    sudo rm -f "$CORE_DROPIN" "$WEB_DROPIN"
    sudo systemctl daemon-reload
}

emergency_restore_main() {
    local rc="$?"
    trap - ERR
    set +e
    echo "ERROR: Stage3 branch deployment failed; restoring service runtime to main" >&2
    remove_dropins
    sudo systemctl restart "$CORE_UNIT"
    sleep 6
    sudo systemctl restart "$WEB_UNIT"
    sleep 1
    assert_main_unit "$CORE_UNIT" "ventilation-core" || true
    assert_main_unit "$WEB_UNIT" "wvc-web-ui" || true
    require_zero_and_shadow "$ROOT/src" "emergency rollback main" 0 || true
    return "$rc"
}

apply_runtime() {
    echo "===== APPLY WEBGUI AUTOMATION STAGE3 BRANCH RUNTIME ====="
    [ "$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)" = "main" ] || fail "production checkout must remain on main"
    [ "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_MAIN" ] || fail "production checkout is not validated main SHA"
    [ -z "$(git -C "$ROOT" status --short)" ] || fail "production main checkout is dirty"
    systemctl is-active --quiet "$CORE_UNIT" || fail "$CORE_UNIT is not active"
    systemctl is-active --quiet "$WEB_UNIT" || fail "$WEB_UNIT is not active"
    systemctl is-active --quiet wvc-host-power.service || fail "wvc-host-power.service is not active"

    local boot_before host_pid_before host_status_before wake_before web_port_before
    boot_before="$(cat /proc/sys/kernel/random/boot_id)"
    host_pid_before="$(unit_pid wvc-host-power.service)"
    host_status_before="$(systemctl show wvc-host-power.service -p StatusText --value)"
    wake_before="$(read_wakealarm)"
    web_port_before="$(proc_env_var "$(unit_pid "$WEB_UNIT")" WVC_WEB_PORT)"
    [ "$web_port_before" = "18091" ] || fail "current production WebGUI port is $web_port_before, expected 18091"

    require_zero_and_shadow "$ROOT/src" "pre-deploy production" 0
    prepare_worktree
    backup_automation_db

    trap emergency_restore_main ERR
    write_dropins

    sudo systemctl restart "$CORE_UNIT"
    wait_unit_active "$CORE_UNIT"
    assert_runtime_unit "$CORE_UNIT" "ventilation-core"
    sleep 6
    require_zero_and_shadow "$WT/src" "Stage3 branch core" 1

    sudo systemctl restart "$WEB_UNIT"
    wait_unit_active "$WEB_UNIT"
    assert_runtime_unit "$WEB_UNIT" "wvc-web-ui"
    wait_web

    local web_pid web_port
    web_pid="$(unit_pid "$WEB_UNIT")"
    web_port="$(proc_env_var "$web_pid" WVC_WEB_PORT)"
    [ "$web_port" = "18091" ] || fail "Stage3 WebGUI effective port=$web_port expected=18091"

    [ "$(cat /proc/sys/kernel/random/boot_id)" = "$boot_before" ] || fail "boot_id changed during deployment"
    [ "$(unit_pid wvc-host-power.service)" = "$host_pid_before" ] || fail "host-power PID changed during deployment"
    [ "$(systemctl show wvc-host-power.service -p StatusText --value)" = "$host_status_before" ] || fail "host-power state changed during deployment"
    [ "$(read_wakealarm)" = "$wake_before" ] || fail "RTC wakealarm changed during deployment"
    require_zero_and_shadow "$WT/src" "post-deploy Stage3 runtime" 1

    trap - ERR
    echo "PASS: Stage3 branch runtime is now persistent through systemd/reboot"
    echo "PASS: WebGUI: http://192.168.1.64:18091/automation"
    echo "PASS: main checkout remains untouched at $EXPECTED_MAIN"
    echo "Runtime SHA: $RUNTIME_SHA"
}

status_runtime() {
    echo "===== WEBGUI AUTOMATION STAGE3 BRANCH RUNTIME STATUS ====="
    echo "main HEAD: $(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
    echo "runtime target SHA: $RUNTIME_SHA"
    echo "core drop-in: $([ -e "$CORE_DROPIN" ] && echo present || echo absent)"
    echo "web drop-in:  $([ -e "$WEB_DROPIN" ] && echo present || echo absent)"
    for unit in "$CORE_UNIT" "$WEB_UNIT"; do
        local pid cwd
        pid="$(unit_pid "$unit" 2>/dev/null || true)"
        cwd=""
        if [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ -d "/proc/$pid" ]; then
            cwd="$(unit_cwd "$pid" 2>/dev/null || true)"
        fi
        echo "$unit: active=$(systemctl is-active "$unit" 2>/dev/null || true) pid=$pid cwd=$cwd"
    done
    if systemctl is-active --quiet "$WEB_UNIT"; then
        local web_pid
        web_pid="$(unit_pid "$WEB_UNIT")"
        echo "WebGUI port: $(proc_env_var "$web_pid" WVC_WEB_PORT)"
    fi
    if [ -d "$WT/.git" ] || git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WT"; then
        echo "runtime worktree HEAD: $(git -C "$WT" rev-parse HEAD 2>/dev/null || true)"
    fi
    curl --silent --show-error --fail --max-time 2 "$WEB_URL/automation" >/dev/null 2>&1 && echo "PASS: /automation reachable" || echo "INFO: /automation not reachable"
}

rollback_runtime() {
    echo "===== ROLLBACK WEBGUI AUTOMATION STAGE3 BRANCH RUNTIME ====="
    if systemctl is-active --quiet "$CORE_UNIT"; then
        local current_cwd
        current_cwd="$(unit_cwd "$(unit_pid "$CORE_UNIT")" 2>/dev/null || true)"
        if [ "$current_cwd" = "$WT" ]; then
            require_zero_and_shadow "$WT/src" "pre-rollback Stage3 runtime" 1
        else
            require_zero_and_shadow "$ROOT/src" "pre-rollback current runtime" 0
        fi
    fi

    remove_dropins
    sudo systemctl restart "$CORE_UNIT"
    wait_unit_active "$CORE_UNIT"
    sleep 6
    assert_main_unit "$CORE_UNIT" "ventilation-core"
    require_zero_and_shadow "$ROOT/src" "rollback production main" 0

    sudo systemctl restart "$WEB_UNIT"
    wait_unit_active "$WEB_UNIT"
    assert_main_unit "$WEB_UNIT" "wvc-web-ui"

    local web_port
    web_port="$(proc_env_var "$(unit_pid "$WEB_UNIT")" WVC_WEB_PORT)"
    [ "$web_port" = "18091" ] || fail "restored production WebGUI port=$web_port expected=18091"
    echo "PASS: services restored to main; no merge was performed"
}

case "${1:-status}" in
    apply)
        apply_runtime
        ;;
    status)
        status_runtime
        ;;
    rollback)
        rollback_runtime
        ;;
    *)
        echo "Usage: $0 {apply|status|rollback}" >&2
        exit 2
        ;;
esac
