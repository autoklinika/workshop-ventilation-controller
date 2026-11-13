#!/usr/bin/env bash
# Install one-shot RTC AUTO resume into the existing WVC host-power sequence.
# Does NOT restart ventilation-core, WebUI, or power off / arm RTC.
set -Eeuo pipefail
umask 077

if [[ "${EUID}" != 0 ]]; then
  echo "ERROR: use sudo bash for scheduled AUTO resume install" >&2
  exit 2
fi

BASE=/home/wentylacja/workshop-ventilation-controller
NEW_GATE="${BASE}/deploy/cm5/wvc-autostart-power-gate.py"
NEW_RESUME="${BASE}/deploy/cm5/wvc-rtc-auto-resume.py"
NEW_UNIT="${BASE}/deploy/systemd/wvc-rtc-auto-resume.service"
GATE=/usr/local/libexec/wvc-autostart-gate.py
RESUME=/usr/local/libexec/wvc-rtc-auto-resume.py
UNIT=/etc/systemd/system/wvc-rtc-auto-resume.service
MARKER_DIR=/var/lib/wvc-scheduled-auto
BACKUP="/var/backups/wvc-rtc-auto-resume-$(date +%Y%m%dT%H%M%S)"
APPLIED=0

rollback() {
  rc=$?
  trap - ERR
  if [[ "$APPLIED" == 1 ]]; then
    echo "Installation failed; rolling back AUTO resume files" >&2
    systemctl disable wvc-rtc-auto-resume.service >/dev/null 2>&1 || true
    for entry in "$GATE" "$RESUME" "$UNIT"; do
      fname="$(basename "$entry")"
      if [[ -f "$BACKUP/$fname.old" ]]; then
        cp -a "$BACKUP/$fname.old" "$entry" || true
      else
        rm -f "$entry" || true
      fi
    done
    systemctl daemon-reload || true
    if [[ -f "$BACKUP/resume-service-was-enabled" ]]; then
      systemctl enable wvc-rtc-auto-resume.service >/dev/null 2>&1 || true
    fi
  fi
  echo "Recovery backup: $BACKUP" >&2
  exit "$rc"
}
trap rollback ERR

echo '[1/5] Non-actuating system and configuration preflight'
for file in "$NEW_GATE" "$NEW_RESUME" "$NEW_UNIT" "$GATE" /usr/local/libexec/wvc-power-schedule.py; do
  test -f "$file"
done
test "$(stat -c %u "$GATE")" = 0
test "$(stat -c %u /usr/local/libexec/wvc-power-schedule.py)" = 0
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-web-ui.service
systemctl is-active --quiet wvc-auto-poweroff.timer
systemctl is-active --quiet wvc-host-power.service
systemctl show -p ExecStart --value wvc-auto-poweroff.service | grep -Fq "$GATE tick"
timedatectl show -p NTPSynchronized --value | grep -Fxq yes
/usr/bin/python3 /usr/local/libexec/wvc-power-schedule.py check
/usr/bin/python3 "$NEW_GATE" plan
/usr/bin/python3 "$NEW_RESUME" inspect
/usr/bin/python3 -m py_compile "$NEW_GATE" "$NEW_RESUME"
systemd-analyze verify "$NEW_UNIT" >/dev/null

# Do not switch binaries during their shutdown minute.
python3 - "$NEW_GATE" <<'PY'
import datetime, importlib.util, json, sys
from zoneinfo import ZoneInfo
# No dynamic execution: only inspect current plan via stdout of the plan command.
import subprocess
text = subprocess.run(
    ['/usr/bin/python3', sys.argv[1], 'plan'],
    capture_output=True, text=True, check=True, timeout=9,
).stdout.strip()
if not text.startswith("WVC_AUTOSTART_PLAN "):
    raise RuntimeError("missing Autostart plan")
plan = json.loads(text[len("WVC_AUTOSTART_PLAN "):])
if plan.get("due_now") is True:
    raise RuntimeError("refusing install during poweroff minute")
if plan.get("autostart_enabled") and plan.get("schedule_enabled") and plan.get("end_local"):
    now = datetime.datetime.now(ZoneInfo("Europe/Warsaw"))
    h, m = map(int, plan["end_local"].split(":"))
    deadline = now.replace(hour=h, minute=m, second=0, microsecond=0)
    diff = (deadline - now).total_seconds()
    if -120 <= diff <= 300:
        raise RuntimeError("refusing install near poweroff boundary")
PY

echo '[2/5] Backup of exact currently installed root-owned files'
install -d -o root -g root -m 0700 "$BACKUP"
for entry in "$GATE" "$RESUME" "$UNIT"; do
  if [[ -f "$entry" ]]; then
    cp -a "$entry" "$BACKUP/$(basename "$entry").old"
  fi
done
if systemctl is-enabled --quiet wvc-rtc-auto-resume.service 2>/dev/null; then
  touch "$BACKUP/resume-service-was-enabled"
fi
systemctl cat wvc-auto-poweroff.timer wvc-auto-poweroff.service > "$BACKUP/existing-power-units.txt"
sha256sum /usr/local/libexec/wvc-power-schedule.py > "$BACKUP/existing-host-power.sha256"

echo '[3/5] Root-owned one-use ticket directory + helper + gate'
APPLIED=1
install -d -o root -g root -m 0700 "$MARKER_DIR"
if [[ -e "$MARKER_DIR/next-wake.json" ]]; then
  echo "ERROR: existing pending resume ticket; refusing installation" >&2
  exit 1
fi
install -o root -g root -m 0755 "$NEW_RESUME" "$RESUME"
install -o root -g root -m 0755 "$NEW_GATE" "$GATE"
install -o root -g root -m 0644 "$NEW_UNIT" "$UNIT"

echo '[4/5] Register next-boot service (DO NOT start it now)'
systemctl daemon-reload
systemctl enable wvc-rtc-auto-resume.service
# A new boot will run the oneshot only when the gate created a ticket.

echo '[5/5] Verify production without changing ventilation'
systemctl is-enabled --quiet wvc-rtc-auto-resume.service
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-web-ui.service
systemctl is-active --quiet wvc-auto-poweroff.timer
systemctl is-active --quiet wvc-host-power.service
test ! -e "$MARKER_DIR/next-wake.json"
test "$(stat -c %u:%a "$MARKER_DIR")" = "0:700"
systemctl show -p ExecStart --value wvc-auto-poweroff.service | grep -Fq "$GATE tick"
/usr/bin/python3 "$GATE" plan
/usr/bin/python3 "$RESUME" inspect
sha256sum -c "$BACKUP/existing-host-power.sha256"
echo "WVC_SCHEDULED_RTC_AUTO_RESUME_INSTALL_PASS"
echo "Backup: $BACKUP"
echo "AUTO will resume only on a validated next scheduled boot if it was AUTO at shutdown."
