#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/wentylacja/workshop-ventilation-controller"
EXPECTED_BRANCH="agent/hmi-sleep-wake-stage15"
TARGET="${WVC_HMI_ADB_TARGET:-192.168.1.39:5555}"
UNIT_SRC="$ROOT/deploy/systemd/wvc-hmi-power.service"
UNIT_DST="/etc/systemd/system/wvc-hmi-power.service"
STATE_DIR="/var/lib/wvc-hmi-power"
BACKUP_ROOT="/var/tmp/wvc-hmi-stage15-backup-$(date +%Y%m%d-%H%M%S)"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

section() {
    echo
    echo "===== $* ====="
}

cd "$ROOT"

section "SOURCE"
BRANCH="$(git branch --show-current)"
HEAD="$(git rev-parse HEAD)"
echo "branch: $BRANCH"
echo "HEAD:   $HEAD"
echo "target: $TARGET"
[ "$BRANCH" = "$EXPECTED_BRANCH" ] || fail "expected branch $EXPECTED_BRANCH"
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"

section "ADB PRECHECK"
[ -x /usr/bin/adb ] || fail "/usr/bin/adb is missing; install Debian package 'adb' first"
echo "adb: $(/usr/bin/adb version | head -1)"

sudo install -d -m 0700 "$STATE_DIR"

echo
echo "HMI must be awake for the first CM5 ADB authorization."
echo "If Android displays an ADB authorization dialog, allow this CM5 key permanently."
sudo env HOME="$STATE_DIR" /usr/bin/adb connect "$TARGET" || true
sudo env HOME="$STATE_DIR" /usr/bin/adb devices || true
read -r -p "Accept the ADB authorization on HMI if requested, then press ENTER... " _

section "DIRECT WAKE CHECK"
sudo env HOME="$STATE_DIR" PYTHONPATH="$ROOT/src" \
    /usr/bin/python3 -m ventilation_core.hmi_power wake \
    --target "$TARGET" --adb /usr/bin/adb --timeout 2.0 --attempts 3 --retry-delay 1.0 --strict

echo "HMI WAKE command: PASS"

section "DIRECT SLEEP CHECK"
sudo env HOME="$STATE_DIR" PYTHONPATH="$ROOT/src" \
    /usr/bin/python3 -m ventilation_core.hmi_power sleep \
    --target "$TARGET" --adb /usr/bin/adb --timeout 2.0 --attempts 2 --retry-delay 0.5 --strict

echo
echo "PHYSICAL CHECK 1: HMI should now be in true Android SLEEP."
read -r -p "Confirm the screen is asleep and press ENTER... " _

section "WAKE FROM TRUE SLEEP"
sudo env HOME="$STATE_DIR" PYTHONPATH="$ROOT/src" \
    /usr/bin/python3 -m ventilation_core.hmi_power wake \
    --target "$TARGET" --adb /usr/bin/adb --timeout 2.0 --attempts 4 --retry-delay 1.0 --strict

echo
echo "PHYSICAL CHECK 2: HMI should be awake again."
read -r -p "Confirm the HMI woke and press ENTER... " _

section "BACKUP + INSTALL SYSTEMD UNIT"
sudo mkdir -p "$BACKUP_ROOT"
if sudo test -e "$UNIT_DST"; then
    sudo cp -a "$UNIT_DST" "$BACKUP_ROOT/wvc-hmi-power.service"
    echo "backup: $UNIT_DST"
else
    echo "not previously installed: $UNIT_DST"
fi
sudo install -m 0644 "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable wvc-hmi-power.service

echo "backup directory: $BACKUP_ROOT"

section "SYSTEMD SLEEP CHECK"
sudo systemctl start wvc-hmi-power.service
systemctl is-active wvc-hmi-power.service >/dev/null || fail "wvc-hmi-power did not become active"
sudo systemctl stop wvc-hmi-power.service
sleep 1
[ "$(systemctl is-active wvc-hmi-power.service || true)" = "inactive" ] \
    || fail "wvc-hmi-power did not stop"

echo
echo "PHYSICAL CHECK 3: systemd ExecStop should have put HMI to SLEEP."
read -r -p "Confirm HMI is asleep and press ENTER... " _

section "SYSTEMD WAKE CHECK"
sudo systemctl start wvc-hmi-power.service
systemctl is-active wvc-hmi-power.service >/dev/null || fail "wvc-hmi-power did not become active"

echo
echo "PHYSICAL CHECK 4: systemd ExecStart should have woken HMI."
read -r -p "Confirm HMI is awake and press ENTER... " _

section "NON-SAFETY ISOLATION CHECK"
systemctl is-active wvc-host-power.service || fail "wvc-host-power is not active"
systemctl is-active ventilation-core.service || fail "ventilation-core is not active"
echo "wvc-host-power: active"
echo "ventilation-core: active"
echo "HMI service did not require cycling the safety/control services."

section "RECENT HMI POWER LOGS"
sudo journalctl -u wvc-hmi-power.service -n 40 --no-pager || true

section "RESULT"
echo "STAGE15 HMI SLEEP/WAKE VALIDATION: PASS"
echo "Validated: direct ADB sleep/wake + systemd ExecStop sleep + ExecStart wake."
echo "HMI remains non-blocking and independent from wvc-host-power/ventilation-core."
echo "No CM5 shutdown or reboot was executed by this harness."
echo "Backup directory: $BACKUP_ROOT"
