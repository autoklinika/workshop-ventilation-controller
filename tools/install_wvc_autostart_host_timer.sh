#!/usr/bin/env bash
# One-time, root-authorized install of the WVC Autostart calendar gate.
# Never restarts ventilation-core or touches GPIO, fans, RTC wakealarm, or HMI.
set -Eeuo pipefail
umask 077

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run this installer as root (sudo bash ...)" >&2
  exit 2
fi

BASE="/home/wentylacja/wvc-autostart-power-integration"
GATE_SRC="${BASE}/deploy/cm5/wvc-autostart-power-gate.py"
TIMER_SRC="${BASE}/deploy/systemd/wvc-auto-poweroff.timer.d/50-autostart-calendar.conf"
SERVICE_SRC="${BASE}/deploy/systemd/wvc-auto-poweroff.service.d/50-autostart-calendar.conf"
GATE_DST="/usr/local/libexec/wvc-autostart-gate.py"
TIMER_DST="/etc/systemd/system/wvc-auto-poweroff.timer.d/50-autostart-calendar.conf"
SERVICE_DST="/etc/systemd/system/wvc-auto-poweroff.service.d/50-autostart-calendar.conf"
LEGACY_SCRIPT="/usr/local/libexec/wvc-power-schedule.py"
BACKUP="/var/backups/wvc-autostart-deploy-$(date +%Y%m%dT%H%M%S)"
APPLIED=0

for path in "$GATE_SRC" "$TIMER_SRC" "$SERVICE_SRC" "$LEGACY_SCRIPT"; do
  test -f "$path" || { echo "ERROR: required file missing: $path" >&2; exit 1; }
done
test -f "/etc/systemd/system/wvc-auto-poweroff.timer"
test -f "/etc/systemd/system/wvc-auto-poweroff.service"
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-web-ui.service
systemctl is-active --quiet wvc-host-power.service

echo "[1/5] Read-only validation of existing RTC and power path"
python3 "$LEGACY_SCRIPT" check

echo "[2/5] Read-only Autostart calendar validation"
PLAN="$(python3 "$GATE_SRC" plan)"
echo "$PLAN"
if echo "$PLAN" | grep -q '"due_now":true'; then
  echo "ERROR: installation refused in an active shutdown minute" >&2
  exit 1
fi
# Also block installing close to the scheduled boundary. Avoid an unexpected
# first timer firing while the operator is still completing the deployment.
python3 - "$PLAN" <<'PY_AUTOSTART_WINDOW'
from datetime import datetime, time
import json
import sys
raw = sys.argv[1]
assert raw.startswith("WVC_AUTOSTART_PLAN ")
plan = json.loads(raw[len("WVC_AUTOSTART_PLAN "):])
if plan["autostart_enabled"] and plan["schedule_enabled"] and plan["end_local"]:
    now = datetime.fromisoformat(plan["now_local"])
    h, m = map(int, plan["end_local"].split(":"))
    target = datetime.combine(now.date(), time(h, m), tzinfo=now.tzinfo)
    seconds = (target - now).total_seconds()
    if -120 <= seconds <= 300:
        raise SystemExit("ERROR: deploy outside the 5-minute shutdown boundary")
PY_AUTOSTART_WINDOW

echo "[3/5] Backing up current systemd files"
install -d -o root -g root -m 0700 "$BACKUP"
cp -a "/etc/systemd/system/wvc-auto-poweroff.timer" "$BACKUP/timer.original"
cp -a "/etc/systemd/system/wvc-auto-poweroff.service" "$BACKUP/service.original"
cp -a "$LEGACY_SCRIPT" "$BACKUP/wvc-power-schedule.original.py"
for item in "$GATE_DST" "$TIMER_DST" "$SERVICE_DST"; do
  base="$(basename "$item")"
  if test -e "$item"; then
    cp -a "$item" "$BACKUP/$base.old"
  fi
done
sha256sum "$LEGACY_SCRIPT" > "$BACKUP/legacy-sha256.before"
{
  date -Is
  systemctl cat wvc-auto-poweroff.timer
  systemctl cat wvc-auto-poweroff.service
} > "$BACKUP/systemd-before.txt"

rollback() {
  local code="$?"
  trap - ERR
  if [[ "$APPLIED" == 1 ]]; then
    echo "ERROR: install failed; attempting rollback" >&2
    systemctl stop wvc-auto-poweroff.timer || true
    for item in "$GATE_DST" "$TIMER_DST" "$SERVICE_DST"; do
      local name
      name="$(basename "$item")"
      if test -f "$BACKUP/$name.old"; then
        cp -a "$BACKUP/$name.old" "$item"
      else
        rm -f "$item"
      fi
    done
    systemctl daemon-reload || true
    systemctl start wvc-auto-poweroff.timer || true
  fi
  echo "Backup: $BACKUP" >&2
  exit "$code"
}
trap rollback ERR

echo "[4/5] Switching the EXISTING timer/service to Autostart gate"
APPLIED=1
systemctl stop wvc-auto-poweroff.timer
install -o root -g root -m 0755 "$GATE_SRC" "$GATE_DST"
install -d -o root -g root -m 0755 "$(dirname "$TIMER_DST")" "$(dirname "$SERVICE_DST")"
install -o root -g root -m 0644 "$TIMER_SRC" "$TIMER_DST"
install -o root -g root -m 0644 "$SERVICE_SRC" "$SERVICE_DST"
python3 -m py_compile "$GATE_DST"
systemctl daemon-reload
systemctl start wvc-auto-poweroff.timer

echo "[5/5] Post-install checks (NO RTC arming, NO shutdown)"
systemctl is-active --quiet wvc-auto-poweroff.timer
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-web-ui.service
systemctl is-active --quiet wvc-host-power.service
systemctl show -p ExecStart --value wvc-auto-poweroff.service | grep -Fq "$GATE_DST tick"
systemctl show -p TimersCalendar --value wvc-auto-poweroff.timer | grep -Fq '*-*-* *:*:00'
python3 "$GATE_DST" plan
sha256sum -c "$BACKUP/legacy-sha256.before"
echo "WVC_AUTOSTART_LIVE_TIMER_INSTALL_PASS"
echo "Backup: $BACKUP"
systemctl list-timers --all wvc-auto-poweroff.timer --no-pager
