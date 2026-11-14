#!/usr/bin/env bash
# Safe, non-disruptive deployment of calendar RTC and AUTO continuity.
set -Eeuo pipefail
umask 077
if [[ "$EUID" != 0 ]]; then
  echo 'ERROR: administrator authorization required' >&2
  exit 2
fi
BASE=/home/wentylacja/workshop-ventilation-controller
PROGRAM=/usr/local/libexec/wvc-schedule-keeper.py
UNIT=/etc/systemd/system/wvc-schedule-keeper.service
TIMER=/etc/systemd/system/wvc-schedule-keeper.timer
ARM_UNIT=/etc/systemd/system/wvc-schedule-keeper-arm.service
STATE=/var/lib/wvc-scheduled-auto
BACKUP="/var/backups/wvc-schedule-keeper-$(date +%Y%m%dT%H%M%S)"
APPLIED=0
rollback() {
  status=$?
  trap - ERR
  if [[ "$APPLIED" == 1 ]]; then
    systemctl disable --now wvc-schedule-keeper.timer >/dev/null 2>&1 || true
    for target in "$PROGRAM" "$UNIT" "$TIMER" "$ARM_UNIT"; do
      name="$(basename "$target")"
      if [[ -f "$BACKUP/$name.old" ]]; then
        cp -a "$BACKUP/$name.old" "$target" || true
      else
        rm -f "$target" || true
      fi
    done
    systemctl daemon-reload || true
    if [[ -f "$BACKUP/timer-was-enabled" ]]; then
      systemctl enable --now wvc-schedule-keeper.timer >/dev/null 2>&1 || true
    fi
  fi
  echo "WVC_KEEPER_ROLLBACK backup=$BACKUP" >&2
  exit "$status"
}
trap rollback ERR
echo '[1/5] Read-only validation'
test -f "$BASE/deploy/cm5/wvc-schedule-keeper.py"
test -f "$BASE/deploy/systemd/wvc-schedule-keeper.service"
test -f "$BASE/deploy/systemd/wvc-schedule-keeper.timer"
test -f "$BASE/deploy/systemd/wvc-schedule-keeper-arm.service"
test -f /sys/class/rtc/rtc0/wakealarm
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-auto-poweroff.timer
systemctl is-active --quiet wvc-host-power.service
timedatectl show -p NTPSynchronized --value | grep -Fxq yes
/usr/bin/python3 -m py_compile "$BASE/deploy/cm5/wvc-schedule-keeper.py"
/usr/bin/python3 "$BASE/deploy/cm5/wvc-schedule-keeper.py" plan
systemd-analyze verify "$BASE/deploy/systemd/wvc-schedule-keeper.service" "$BASE/deploy/systemd/wvc-schedule-keeper.timer" "$BASE/deploy/systemd/wvc-schedule-keeper-arm.service" >/dev/null
echo '[2/5] Backup current units'
install -d -o root -g root -m 0700 "$BACKUP"
for target in "$PROGRAM" "$UNIT" "$TIMER" "$ARM_UNIT"; do
  if [[ -f "$target" ]]; then
    cp -a "$target" "$BACKUP/$(basename "$target").old"
  fi
done
if systemctl is-enabled --quiet wvc-schedule-keeper.timer 2>/dev/null; then
  touch "$BACKUP/timer-was-enabled"
fi
echo '[3/5] Install root-owned keeper and state'
install -d -o root -g root -m 0700 "$STATE"
APPLIED=1
install -o root -g root -m 0755 "$BASE/deploy/cm5/wvc-schedule-keeper.py" "$PROGRAM.new"
mv -f "$PROGRAM.new" "$PROGRAM"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-keeper.service" "$UNIT"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-keeper.timer" "$TIMER"
install -o root -g root -m 0644 "$BASE/deploy/systemd/wvc-schedule-keeper-arm.service" "$ARM_UNIT"
echo '[4/5] Enable timer only; no ventilation restart or CM5 shutdown'
systemctl daemon-reload
systemctl enable --now wvc-schedule-keeper.timer
echo '[5/5] Reconcile RTC readback and verify'
/usr/bin/python3 "$PROGRAM" arm
systemctl is-enabled --quiet wvc-schedule-keeper.timer
systemctl is-active --quiet wvc-schedule-keeper.timer
systemctl is-active --quiet ventilation-core.service
systemctl is-active --quiet wvc-auto-poweroff.timer
echo "WVC_SCHEDULE_KEEPER_INSTALL_PASS"
echo "Backup: $BACKUP"
