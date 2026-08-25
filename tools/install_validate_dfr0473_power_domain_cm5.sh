#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/wentylacja/workshop-ventilation-controller"
EXPECTED_BRANCH="agent/power-domain-dfr0473-stage14"
HOST_POWER_UNIT="/etc/systemd/system/wvc-host-power.service"
CORE_UNIT="/etc/systemd/system/ventilation-core.service"
LOGIND_DROPIN_DIR="/etc/systemd/logind.conf.d"
LOGIND_DROPIN="$LOGIND_DROPIN_DIR/50-wvc-power-button.conf"
BACKUP_ROOT="/var/tmp/wvc-dfr0473-stage14-backup-$(date +%Y%m%d-%H%M%S)"

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
[ "$BRANCH" = "$EXPECTED_BRANCH" ] || fail "expected branch $EXPECTED_BRANCH"
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"

section "PRECHECK SERVICES"
systemctl is-active ventilation-core.service || fail "ventilation-core is not active"
systemctl is-active wvc-host-power.service || fail "wvc-host-power is not active"

section "FORCE LOCAL SAFE STOP"
STOP_JSON="$(PYTHONPATH=src python3 -m ventilation_core.ctl stop)" || fail "core STOP command failed"
printf '%s\n' "$STOP_JSON" | python3 -c '
import json,sys
p=json.load(sys.stdin)
if p.get("ok") is not True:
    raise SystemExit("STOP response is not ok")
s=p.get("state") or {}
sp=s.get("setpoints") or {}
if s.get("mode") != "STOP":
    raise SystemExit(f"mode is not STOP: {s.get(chr(109)+chr(111)+chr(100)+chr(101))!r}")
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit(f"outputs are not 0 V: {sp!r}")
if s.get("output_state_known") is not True:
    raise SystemExit("output_state_known is not true")
print("SAFE STOP / 0 V: PASS")
'

section "BACKUP INSTALLED CONFIG"
sudo mkdir -p "$BACKUP_ROOT"
for path in "$HOST_POWER_UNIT" "$CORE_UNIT" "$LOGIND_DROPIN"; do
    if sudo test -e "$path"; then
        sudo cp -a "$path" "$BACKUP_ROOT/$(basename "$path")"
        echo "backup: $path"
    else
        echo "not previously installed: $path"
    fi
done
echo "backup directory: $BACKUP_ROOT"

section "INSTALL STAGE14 UNITS"
sudo install -m 0644 deploy/systemd/wvc-host-power.service "$HOST_POWER_UNIT"
sudo install -m 0644 deploy/systemd/ventilation-core.service "$CORE_UNIT"
sudo mkdir -p "$LOGIND_DROPIN_DIR"
sudo install -m 0644 deploy/systemd/logind.conf.d/50-wvc-power-button.conf "$LOGIND_DROPIN"
sudo systemctl daemon-reload

echo "NOTE: systemd-logind is NOT restarted by this harness."
echo "The POWER-button policy will be verified after the later controlled reboot/boot cycle."

section "VERIFY UNIT GRAPH"
systemctl cat wvc-host-power.service | grep -F -- '--power-domain-line GPIO22' >/dev/null \
    || fail "installed host-power unit does not select GPIO22"
systemctl cat ventilation-core.service | grep -F 'Requires=wvc-host-power.service' >/dev/null \
    || fail "installed core unit does not require host-power"
systemctl cat ventilation-core.service | grep -F 'After=local-fs.target wvc-host-power.service' >/dev/null \
    || fail "installed core unit does not start after host-power"
echo "systemd dependency/config: PASS"

section "CONTROLLED POWER-DOMAIN OFF TEST"
echo "Stopping wvc-host-power.service. Because ventilation-core Requires/After it,"
echo "the core must stop first and GPIO22 must then return DFR0473 to OFF."
sudo systemctl stop wvc-host-power.service
sleep 1

HOST_STATE="$(systemctl is-active wvc-host-power.service || true)"
CORE_STATE="$(systemctl is-active ventilation-core.service || true)"
echo "wvc-host-power: $HOST_STATE"
echo "ventilation-core: $CORE_STATE"
[ "$HOST_STATE" = "inactive" ] || fail "wvc-host-power did not stop"
[ "$CORE_STATE" = "inactive" ] || fail "ventilation-core did not stop with required power-domain service"

echo
echo "PHYSICAL CHECK 1: DFR0473 should now be OFF (relay released / relay LED OFF)."
read -r -p "Confirm physically and press ENTER to continue... " _

section "CONTROLLED POWER-DOMAIN ON + CORE START TEST"
echo "Starting ventilation-core.service. systemd must first start wvc-host-power,"
echo "command GPIO22 HIGH, wait for 12 V stabilization, then start the core."
sudo systemctl start ventilation-core.service
sleep 2

systemctl is-active wvc-host-power.service || fail "wvc-host-power did not become active"
systemctl is-active ventilation-core.service || fail "ventilation-core did not become active"

echo
echo "PHYSICAL CHECK 2: DFR0473 should now be ON (relay energized / relay LED ON)."
read -r -p "Confirm physically and press ENTER to continue... " _

section "POST-START LOCAL SAFE STATE"
STATUS_JSON="$(PYTHONPATH=src python3 -m ventilation_core.ctl status)" || fail "core status failed"
printf '%s\n' "$STATUS_JSON" | python3 -c '
import json,sys
p=json.load(sys.stdin)
s=p.get("state") or {}
sp=s.get("setpoints") or {}
print("mode:", s.get("mode"))
print("supply_voltage:", sp.get("supply_voltage"))
print("extract_voltage:", sp.get("extract_voltage"))
print("output_state_known:", s.get("output_state_known"))
if s.get("mode") != "STOP":
    raise SystemExit("core did not return in STOP after service start")
if sp.get("supply_voltage") != 0.0 or sp.get("extract_voltage") != 0.0:
    raise SystemExit("core outputs are not 0 V after service start")
if s.get("output_state_known") is not True:
    raise SystemExit("output state is not known after service start")
print("post-start STOP / 0 V: PASS")
'

section "RECENT POWER-DOMAIN LOGS"
sudo journalctl -u wvc-host-power.service -n 30 --no-pager

section "RESULT"
echo "STAGE14 NON-DESTRUCTIVE HARDWARE VALIDATION: PASS"
echo "No host shutdown or reboot was executed."
echo "Next physical test is the controlled GUI shutdown, followed by PWR_BUT startup."
echo "Backup directory: $BACKUP_ROOT"
