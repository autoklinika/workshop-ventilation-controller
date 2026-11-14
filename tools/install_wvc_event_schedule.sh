#!/usr/bin/env bash
# Event-driven WVC RTC and AUTO scheduling (no minute polling).
# Installs boot and calendar-change events plus one-time systemd timers.
# Never requests manual AUTO, fan writes, or host shutdown at installation.
set -Eeuo pipefail
umask 077

if [[ "$EUID" != 0 ]]; then
  echo "ERROR: administrator authorization required (sudo bash ...)" >&2
  exit 2
fi

BASE=/home/wentylacja/workshop-ventilation-controller
RUNTIME_WEB=/home/wentylacja/wvc-webui-physical-mode/src/ventilation_core/web/app.py
SOURCE="$BASE/deploy/cm5/wvc-schedule-keeper.py"
PROGRAM=/usr/local/libexec/wvc-schedule-keeper.py
ARM=/etc/systemd/system/wvc-schedule-keeper-arm.service
BOOT=/etc/systemd/system/wvc-schedule-boot.service
CHANGE=/etc/systemd/system/wvc-schedule-change.service
PATH_UNIT=/etc/systemd/system/wvc-schedule-change.path
MARKER=/srv/wvc-data/workshop-ventilation/autostart-changed.signal
STATE=/var/lib/wvc-scheduled-auto
BACKUP="/var/backups/wvc-event-schedule-$(date +%Y%m%dT%H%M%S)"
APPLIED=0

rollback() {
  local status="$?"
  trap - ERR
  if [[ "$APPLIED" == 1 ]]; then
    echo "ERROR: event scheduler installation failed; restoring old state" >&2
    systemctl disable --now wvc-schedule-change.path >/dev/null 2>&1 || true
    systemctl disable wvc-schedule-boot.service >/dev/null 2>&1 || true
    # Never leave new transient STOP timers active alongside the restored
    # legacy minute timer (would otherwise issue duplicate shutdown requests).
    while IFS= read -r timer; do
      if [[ -n "$timer" ]]; then systemctl stop "$timer" || true; fi
    done < <(systemctl list-units --all --type=timer --no-pager --plain --no-legend 2>/dev/null \
      | grep -oE '^wvc-scheduled-(start|close)-[0-9]{8}-[0-9]{4}-[0-9]+\.timer' || true)
    for target in "$PROGRAM" "$ARM" "$BOOT" "$CHANGE" "$PATH_UNIT"; do
      local name
      name="$(basename "$target")"
      if [[ -f "$BACKUP/$name.old" ]]; then
        cp -a "$BACKUP/$name.old" "$target" || true
      else
        rm -f "$target" || true
      fi
    done
    if [[ ! -f "$BACKUP/marker-existed" ]]; then
      rm -f "$MARKER" || true
    fi
    systemctl daemon-reload || true
    if [[ -f "$BACKUP/old-poweroff-enabled" ]]; then
      systemctl enable --now wvc-auto-poweroff.timer || true
    fi
    if [[ -f "$BACKUP/old-keeper-enabled" ]]; then
      systemctl enable --now wvc-schedule-keeper.timer || true
    fi
    if [[ -f "$BACKUP/change-was-enabled" ]]; then
      systemctl enable --now wvc-schedule-change.path || true
    fi
    if [[ -f "$BACKUP/boot-was-enabled" ]]; then
      systemctl enable wvc-schedule-boot.service || true
    fi
    echo "ERROR: rollback may leave transient one-time timers; inspect systemctl list-timers." >&2
  fi
  echo "Backup: $BACKUP" >&2
  exit "$status"
}
trap rollback ERR

echo "[1/5] Safe read-only preflight"
for file in "$SOURCE" "$BASE/deploy/systemd/wvc-schedule-keeper-arm.service"   "$BASE/deploy/systemd/wvc-schedule-boot.service"   "$BASE/deploy/systemd/wvc-schedule-change.service"   "$BASE/deploy/systemd/wvc-schedule-change.path" "$RUNTIME_WEB"   /usr/local/libexec/wvc-autostart-gate.py /usr/local/libexec/wvc-power-schedule.py; do
  test -f "$file" || { echo "Missing: $file" >&2; exit 1; }
done
grep -Fq 'autostart-changed.signal' "$RUNTIME_WEB" || {
  echo "Live WebUI must have saved-calendar notifier before installation" >&2
  exit 1
}
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-web-ui.service
systemctl is-active --quiet wvc-auto-poweroff.timer
systemctl is-active --quiet wvc-host-power.service
timedatectl show -p NTPSynchronized --value | grep -Fxq yes
test -d "$(dirname "$MARKER")"
command -v systemd-run >/dev/null
python3 -m py_compile "$SOURCE"
python3 "$SOURCE" plan
/usr/bin/python3 /usr/local/libexec/wvc-power-schedule.py check
# Installation must not cross a scheduled shutdown minute.
python3 - "$SOURCE" <<'PY_CHECK'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import importlib.util, sys
spec=importlib.util.spec_from_file_location("wvc_preflight_calendar", sys.argv[1])
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
now=datetime.now(ZoneInfo("Europe/Warsaw"))
info=module.plan(now, lambda y: module.core_request({"command":"autostart","year":y}))
end=info.get("end_today_local")
if end is not None and abs((datetime.fromisoformat(end)-now).total_seconds()) <= 300:
    raise SystemExit("Refusing install within 5 minutes of scheduled close")
PY_CHECK
systemd-analyze verify "$BASE/deploy/systemd/wvc-schedule-boot.service"   "$BASE/deploy/systemd/wvc-schedule-change.service"   "$BASE/deploy/systemd/wvc-schedule-change.path"   "$BASE/deploy/systemd/wvc-schedule-keeper-arm.service" >/dev/null

echo "[2/5] Save all existing root-owned units and activation state"
install -d -o root -g root -m 0700 "$BACKUP"
for target in "$PROGRAM" "$ARM" "$BOOT" "$CHANGE" "$PATH_UNIT"; do
  if [[ -f "$target" ]]; then cp -a "$target" "$BACKUP/$(basename "$target").old"; fi
done
cp -a "$RUNTIME_WEB" "$BACKUP/live-web-app.py"
systemctl cat wvc-auto-poweroff.timer wvc-auto-poweroff.service > "$BACKUP/power-units-before.txt"
if [[ -e "$MARKER" ]]; then touch "$BACKUP/marker-existed"; fi
if systemctl is-enabled --quiet wvc-auto-poweroff.timer; then touch "$BACKUP/old-poweroff-enabled"; fi
if systemctl is-enabled --quiet wvc-schedule-keeper.timer 2>/dev/null; then touch "$BACKUP/old-keeper-enabled"; fi
if systemctl is-enabled --quiet wvc-schedule-change.path 2>/dev/null; then touch "$BACKUP/change-was-enabled"; fi
if systemctl is-enabled --quiet wvc-schedule-boot.service 2>/dev/null; then touch "$BACKUP/boot-was-enabled"; fi

echo "[3/5] Install root-only event planner and save-notification watcher"
APPLIED=1
install -d -o root -g root -m 0700 "$STATE"
install -o root -g root -m 0755 "$SOURCE" "$PROGRAM.new"
mv -f "$PROGRAM.new" "$PROGRAM"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-keeper-arm.service" "$ARM"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-boot.service" "$BOOT"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-change.service" "$CHANGE"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-change.path" "$PATH_UNIT"
if [[ ! -e "$MARKER" ]]; then
  install -o wentylacja -g wentylacja -m 0640 /dev/null "$MARKER"
fi
systemctl daemon-reload

echo "[4/5] Arm RTC and schedule exact one-time start + close before disabling polling"
systemctl enable wvc-schedule-boot.service
systemctl enable --now wvc-schedule-change.path
python3 "$PROGRAM" sync
python3 "$PROGRAM" plan
echo "One-time timers:"
systemctl list-timers --all --no-pager | grep -E 'wvc-scheduled-(start|close)' || {
  echo "ERROR: no exact next start/close was scheduled" >&2
  exit 1
}
for kind in start close; do
  if ! systemctl list-timers --all --no-pager --no-legend |
       grep -qE "wvc-scheduled-${kind}-[0-9]{8}-[0-9]{4}-[0-9]+[.]timer"; then
    echo "ERROR: one-time ${kind} timer is missing; keeping legacy timer" >&2
    exit 1
  fi
done
systemctl disable --now wvc-auto-poweroff.timer
if systemctl is-enabled --quiet wvc-schedule-keeper.timer 2>/dev/null; then
  systemctl disable --now wvc-schedule-keeper.timer
fi
# Only WebUI is restarted to activate its calendar-save notification hook.
# We deliberately DO NOT restart ventilation-core, wvc-host-power or HMI.
systemctl restart wvc-web-ui.service

echo "[5/5] Wait for WebGUI HTTP readiness and verify live services"
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-host-power.service
# Type=simple becomes 'active' before the HTTP listener binds to port 18091.
# Restarting WebGUI can take several seconds. A transient connection refusal
# is not a failure of the RTC or the already verified START/STOP timers.
WEB_READY=0
for attempt in $(seq 1 45); do
  if systemctl is-active --quiet wvc-web-ui.service &&
     curl -fsS --connect-timeout 1 --max-time 2 \
       http://127.0.0.1:18091/api/v1/health >/dev/null 2>&1; then
    WEB_READY=1
    echo "WVC_WEBGUI_POST_RESTART_READY_PASS attempt=${attempt}"
    break
  fi
  sleep 1
done
if [[ "$WEB_READY" != 1 ]]; then
  echo "ERROR: WebGUI did not become ready within 45 seconds" >&2
  systemctl status wvc-web-ui.service --no-pager -l >&2 || true
  exit 1
fi
systemctl is-active --quiet wvc-schedule-change.path
systemctl is-enabled --quiet wvc-schedule-boot.service
if systemctl is-active --quiet wvc-auto-poweroff.timer; then
  echo "ERROR: old minute-based poweroff timer is still active" >&2
  exit 1
fi
python3 "$PROGRAM" plan
echo "RTC wakealarm: $(cat /sys/class/rtc/rtc0/wakealarm)"
echo "WVC_EVENT_SCHEDULE_INSTALL_PASS"
echo "Backup: $BACKUP"
