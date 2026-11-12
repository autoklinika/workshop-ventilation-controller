#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/home/wentylacja/wvc-power-schedule
SCRIPT=/usr/local/libexec/wvc-power-schedule.py
SERVICE=/etc/systemd/system/wvc-auto-poweroff.service
TIMER=/etc/systemd/system/wvc-auto-poweroff.timer

if [[ $(id -u) -ne 0 ]]; then
  echo "ERROR: uruchom: sudo bash $ROOT/tools/install_wvc_power_schedule.sh" >&2
  exit 1
fi

# First validate hardware and EEPROM without changing the system.
python3 "$ROOT/tools/wvc_power_schedule.py" check
systemd-analyze verify "$ROOT/deploy/systemd/wvc-auto-poweroff.service" "$ROOT/deploy/systemd/wvc-auto-poweroff.timer"
install -d -m 0755 /usr/local/libexec
install -m 0755 "$ROOT/tools/wvc_power_schedule.py" "$SCRIPT"
install -m 0644 "$ROOT/deploy/systemd/wvc-auto-poweroff.service" "$SERVICE"
install -m 0644 "$ROOT/deploy/systemd/wvc-auto-poweroff.timer" "$TIMER"
systemctl daemon-reload

# Verify real RTC programming before activation. This action does NOT shut down the host.
python3 "$SCRIPT" arm-only
systemctl enable --now wvc-auto-poweroff.timer
systemctl is-enabled --quiet wvc-auto-poweroff.timer
systemctl is-active --quiet wvc-auto-poweroff.timer

echo "===== HARMONOGRAM ====="
systemctl list-timers --all wvc-auto-poweroff.timer --no-pager
echo "===== RTC ====="
cat /sys/class/rtc/rtc0/wakealarm
echo "===== WVC POWER STATUS ====="
systemctl is-active wvc-host-power wvc-hmi-power ventilation-core wvc-web-ui
echo "WVC_POWER_SCHEDULE_DEPLOY_PASS"
echo "Nastepne wylaczenie: dzisiaj o 19:00 czasu Europe/Warsaw, jezeli system jest wlaczony."
echo "Nastepne uruchomienie po wylaczeniu: jutro o 08:00 (RTC)."
