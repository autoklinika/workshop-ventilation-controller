#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/wentylacja/workshop-ventilation-controller"
DATA_ROOT="/srv/wvc-data"
USER_HOME="/home/wentylacja"
VSCODE_SOURCE="$USER_HOME/.vscode-server"
VSCODE_TARGET="$DATA_ROOT/development/vscode-server"
OLD_LEASE="/var/lib/misc/dnsmasq-wvc.leases"
NEW_LEASE="/run/wvc-sensor-service/dnsmasq-wvc.leases"
APPLY=0

usage() {
  cat <<'EOF'
Usage: sudo ./tools/apply_cm5_emmc_write_hardening_stage2.sh [--apply]

Without --apply this script performs read-only prechecks and prints the plan.
With --apply it:
  * moves WVC DHCP lease writes from eMMC to /run (tmpfs),
  * keeps the legacy lease path as a symlink for old diagnostics,
  * restarts only the DHCP and service-agent services,
  * relocates VS Code Server data to the SN770 NVMe and leaves an eMMC rollback
    directory in place until a later cleanup.

The ventilation-core service is not stopped or restarted by this script.
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -d "$ROOT" ]] || { echo "Repository not found: $ROOT" >&2; exit 1; }
mountpoint -q "$DATA_ROOT" || { echo "NVMe data tier is not mounted at $DATA_ROOT" >&2; exit 1; }
SOURCE="$(findmnt -n -o SOURCE "$DATA_ROOT")"
FSTYPE="$(findmnt -n -o FSTYPE "$DATA_ROOT")"
[[ "$SOURCE" == /dev/nvme* ]] || { echo "$DATA_ROOT is not backed by NVMe: $SOURCE" >&2; exit 1; }
[[ "$FSTYPE" == ext4 ]] || { echo "$DATA_ROOT is not ext4: $FSTYPE" >&2; exit 1; }

cd "$ROOT"

echo "===== EMMC WRITE HARDENING STAGE 2 PRECHECK ====="
echo "repo HEAD:       $(git rev-parse HEAD)"
echo "data source:     $SOURCE"
echo "DHCP lease RAM:  $NEW_LEASE"
echo "VS Code target:  $VSCODE_TARGET"
echo
findmnt "$DATA_ROOT"

echo
if [[ -L "$VSCODE_SOURCE" ]]; then
  echo "VS Code source is already a symlink -> $(readlink "$VSCODE_SOURCE")"
elif [[ -d "$VSCODE_SOURCE" ]]; then
  echo "VS Code source exists on eMMC: $(du -sh "$VSCODE_SOURCE" | awk '{print $1}')"
else
  echo "VS Code source does not exist yet. A fail-closed symlink will be created."
fi

if (( ! APPLY )); then
  echo
  echo "PRECHECK PASS. No data changed. Re-run with --apply to perform Stage 2."
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "--apply requires root (use sudo)." >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. DHCP lease state -> /run (tmpfs)
# ---------------------------------------------------------------------------
install -m 0644 \
  "$ROOT/deploy/cm5/wifi/dnsmasq/wvc-sensor-service.conf" \
  /etc/dnsmasq.d/wvc-sensor-service.conf
install -m 0644 \
  "$ROOT/deploy/cm5/wifi/systemd/wvc-sensor-dhcp.service" \
  /etc/systemd/system/wvc-sensor-dhcp.service

install -d -m 0755 /run/wvc-sensor-service /var/lib/misc

# Preserve the current lease table in RAM during the transition so OTA fallback
# remains useful even before clients renew their leases.
if [[ -f "$OLD_LEASE" && ! -L "$OLD_LEASE" ]]; then
  cp -a "$OLD_LEASE" "$NEW_LEASE"
fi

rm -f "$OLD_LEASE"
ln -s "$NEW_LEASE" "$OLD_LEASE"

systemctl daemon-reload
systemctl restart wvc-sensor-dhcp.service
systemctl restart wvc-service-agent.service

# ---------------------------------------------------------------------------
# 2. VS Code Server -> NVMe
# ---------------------------------------------------------------------------
install -d -o wentylacja -g wentylacja -m 0750 "$DATA_ROOT/development"
install -d -o wentylacja -g wentylacja -m 0750 "$VSCODE_TARGET"

if [[ -L "$VSCODE_SOURCE" ]]; then
  CURRENT_TARGET="$(readlink -f "$VSCODE_SOURCE" 2>/dev/null || true)"
  EXPECTED_TARGET="$(readlink -f "$VSCODE_TARGET")"
  [[ "$CURRENT_TARGET" == "$EXPECTED_TARGET" ]] || {
    echo "REFUSING: $VSCODE_SOURCE points to unexpected target: $CURRENT_TARGET" >&2
    exit 1
  }
elif [[ -d "$VSCODE_SOURCE" ]]; then
  # Copy first, then atomically replace the visible path with a symlink.
  # Existing VS Code processes may keep already-open files in the rollback
  # directory until the Remote session reconnects; new opens follow the NVMe
  # symlink. We intentionally do not kill the current development session.
  cp -a "$VSCODE_SOURCE/." "$VSCODE_TARGET/"
  chown -R wentylacja:wentylacja "$VSCODE_TARGET"

  STAMP="$(date +%Y%m%d-%H%M%S)"
  BACKUP="$USER_HOME/.vscode-server.emmc-rollback-$STAMP"
  mv "$VSCODE_SOURCE" "$BACKUP"
  ln -s "$VSCODE_TARGET" "$VSCODE_SOURCE"
  chown -h wentylacja:wentylacja "$VSCODE_SOURCE"
  echo "VS Code eMMC rollback snapshot: $BACKUP"
else
  ln -s "$VSCODE_TARGET" "$VSCODE_SOURCE"
  chown -h wentylacja:wentylacja "$VSCODE_SOURCE"
fi

sync

echo
echo "===== EMMC WRITE HARDENING STAGE 2 APPLIED ====="
echo "DHCP config:"
grep -F 'dhcp-leasefile=' /etc/dnsmasq.d/wvc-sensor-service.conf
ls -l "$OLD_LEASE" || true
systemctl is-active wvc-sensor-dhcp.service
systemctl is-active wvc-service-agent.service

echo
echo "VS Code:"
ls -ld "$VSCODE_SOURCE" "$VSCODE_TARGET"

echo
echo "IMPORTANT: reconnect the VS Code Remote session once after this command."
echo "That closes any old file descriptors still pointing at the eMMC rollback directory."
echo "Then run: sudo ./tools/validate_cm5_emmc_write_hardening_stage2.sh"
