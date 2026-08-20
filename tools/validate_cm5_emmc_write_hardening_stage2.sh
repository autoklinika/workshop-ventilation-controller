#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="/srv/wvc-data"
VSCODE_SOURCE="/home/wentylacja/.vscode-server"
VSCODE_TARGET="$DATA_ROOT/development/vscode-server"
OLD_LEASE="/var/lib/misc/dnsmasq-wvc.leases"
NEW_LEASE="/run/wvc-sensor-service/dnsmasq-wvc.leases"
FAIL=0

pass() { echo "PASS: $*"; }
info() { echo "INFO: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

if mountpoint -q "$DATA_ROOT"; then
  pass "$DATA_ROOT is mounted"
else
  fail "$DATA_ROOT is not mounted"
fi

SOURCE="$(findmnt -n -o SOURCE "$DATA_ROOT" 2>/dev/null || true)"
[[ "$SOURCE" == /dev/nvme* ]] \
  && pass "data tier is NVMe ($SOURCE)" \
  || fail "data tier is not NVMe: $SOURCE"

ROOT_SOURCE="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
[[ "$ROOT_SOURCE" == /dev/mmcblk* ]] \
  && pass "OS root remains on eMMC ($ROOT_SOURCE)" \
  || fail "unexpected root filesystem: $ROOT_SOURCE"

if grep -Fqx "dhcp-leasefile=$NEW_LEASE" /etc/dnsmasq.d/wvc-sensor-service.conf 2>/dev/null; then
  pass "dnsmasq leases are configured in RAM"
else
  fail "dnsmasq does not use $NEW_LEASE"
fi

if systemctl cat wvc-sensor-dhcp.service 2>/dev/null | grep -Fq 'RuntimeDirectory=wvc-sensor-service'; then
  pass "DHCP service owns volatile runtime directory"
else
  fail "wvc-sensor-dhcp.service lacks RuntimeDirectory=wvc-sensor-service"
fi

if [[ -L "$OLD_LEASE" ]]; then
  LINK="$(readlink "$OLD_LEASE")"
  [[ "$LINK" == "$NEW_LEASE" ]] \
    && pass "legacy DHCP lease path is a RAM compatibility symlink" \
    || fail "legacy lease symlink points to $LINK"
else
  fail "$OLD_LEASE is not a symlink"
fi

RUN_FSTYPE="$(findmnt -n -o FSTYPE -T /run 2>/dev/null || true)"
[[ "$RUN_FSTYPE" == tmpfs ]] \
  && pass "/run is tmpfs" \
  || fail "/run filesystem is $RUN_FSTYPE, expected tmpfs"

for unit in wvc-sensor-dhcp.service wvc-service-agent.service ventilation-core.service; do
  if systemctl is-active --quiet "$unit"; then
    pass "$unit active"
  else
    fail "$unit not active"
  fi
done

if [[ -L "$VSCODE_SOURCE" ]]; then
  REAL_SOURCE="$(readlink -f "$VSCODE_SOURCE" 2>/dev/null || true)"
  REAL_TARGET="$(readlink -f "$VSCODE_TARGET" 2>/dev/null || true)"
  if [[ -n "$REAL_SOURCE" && "$REAL_SOURCE" == "$REAL_TARGET" ]]; then
    pass "VS Code Server path resolves to NVMe target"
  else
    fail "VS Code Server symlink target mismatch: $REAL_SOURCE"
  fi
else
  fail "$VSCODE_SOURCE is not a symlink"
fi

if [[ -d "$VSCODE_TARGET" ]]; then
  TARGET_SOURCE="$(findmnt -n -o SOURCE -T "$VSCODE_TARGET" 2>/dev/null || true)"
  [[ "$TARGET_SOURCE" == /dev/nvme* ]] \
    && pass "VS Code Server data is backed by NVMe ($TARGET_SOURCE)" \
    || fail "VS Code Server target is backed by $TARGET_SOURCE"
else
  fail "VS Code Server NVMe target is missing"
fi

# After one Remote reconnect there should be no process retaining an open file
# from the eMMC rollback copy. Inspect /proc directly so lsof is not required.
OPEN_ROLLBACK=0
for fd in /proc/[0-9]*/fd/*; do
  [[ -e "$fd" || -L "$fd" ]] || continue
  target="$(readlink "$fd" 2>/dev/null || true)"
  case "$target" in
    /home/wentylacja/.vscode-server.emmc-rollback-*)
      if (( OPEN_ROLLBACK == 0 )); then
        echo "Open VS Code rollback descriptors:" >&2
      fi
      echo "  $fd -> $target" >&2
      OPEN_ROLLBACK=1
      ;;
  esac
done
if (( OPEN_ROLLBACK )); then
  fail "VS Code Remote still has open descriptors on the eMMC rollback copy; reconnect Remote once"
else
  pass "no active VS Code descriptor points to an eMMC rollback copy"
fi

if grep -Rqs '^Storage=volatile$' /etc/systemd/journald.conf.d; then
  pass "journald persistent churn is disabled"
else
  fail "journald volatile protection is missing"
fi

if swapon --noheadings --show=NAME 2>/dev/null | grep -q '^/dev/zram0$'; then
  pass "swap is zram, not eMMC"
else
  info "zram swap was not detected"
fi

echo
echo "===== INTENTIONALLY LOW-WRITE EMMC CONFIG ====="
for path in \
  /var/lib/workshop-ventilation/automation.sqlite3 \
  /var/lib/workshop-ventilation/zigbee-roles.json; do
  if [[ -e "$path" ]]; then
    stat -c '%n size=%s mtime=%y' "$path"
  else
    info "$path not present"
  fi
done

echo
echo "===== FILESYSTEMS ====="
findmnt /
findmnt "$DATA_ROOT" || true

echo
if (( FAIL )); then
  echo "EMMC WRITE HARDENING STAGE 2: FAIL" >&2
  exit 1
fi

echo "EMMC WRITE HARDENING STAGE 2: PASS"
