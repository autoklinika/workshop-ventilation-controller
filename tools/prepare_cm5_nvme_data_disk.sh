#!/usr/bin/env bash
set -euo pipefail

DEVICE="/dev/nvme0n1"
MOUNTPOINT="/srv/wvc-data"
LABEL="WVC_DATA"
APPLY=0

usage() {
  cat <<'EOF'
Usage: sudo ./tools/prepare_cm5_nvme_data_disk.sh [--device /dev/nvme0n1] [--apply]

Without --apply this script is read-only and prints the planned destructive work.
With --apply it DESTROYS the selected disk, creates one GPT/ext4 partition, labels
it WVC_DATA, mounts it at /srv/wvc-data and installs an UUID-based /etc/fstab entry.
EOF
}

while (($#)); do
  case "$1" in
    --device) DEVICE="${2:?missing device}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for command in lsblk findmnt mountpoint wipefs sfdisk udevadm blkid mkfs.ext4 mount systemctl python3; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done

[[ -b "$DEVICE" ]] || { echo "Not a block device: $DEVICE" >&2; exit 1; }

ROOT_SOURCE="$(findmnt -n -o SOURCE /)"
ROOT_PARENT="$(lsblk -nro PKNAME "$ROOT_SOURCE" 2>/dev/null | head -n1 || true)"
DEVICE_NAME="$(basename "$DEVICE")"
if [[ "$ROOT_SOURCE" == "$DEVICE"* || "$ROOT_PARENT" == "$DEVICE_NAME" ]]; then
  echo "REFUSING: selected device backs the root filesystem: $ROOT_SOURCE" >&2
  exit 1
fi

MODEL="$(lsblk -dn -o MODEL "$DEVICE" | sed 's/[[:space:]]*$//')"
SIZE="$(lsblk -dn -o SIZE "$DEVICE")"
echo "===== NVME DATA DISK PRECHECK ====="
echo "device:      $DEVICE"
echo "model:       $MODEL"
echo "size:        $SIZE"
echo "root:        $ROOT_SOURCE"
echo "mountpoint:  $MOUNTPOINT"
echo
lsblk -f "$DEVICE"

echo
cat <<EOF
Planned layout:
  $DEVICE -> GPT -> one ext4 partition, label $LABEL
  mount   -> $MOUNTPOINT
  options -> defaults,noatime,nofail,x-systemd.device-timeout=10s

THIS ERASES ALL EXISTING WINDOWS/NTFS DATA ON $DEVICE.
EOF

if (( ! APPLY )); then
  echo
  echo "DRY RUN ONLY. Re-run with --apply when the selected device is confirmed."
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "--apply requires root (use sudo)." >&2; exit 1; }

while read -r partition mount_path; do
  [[ -z "${mount_path:-}" ]] && continue
  umount "$partition"
done < <(lsblk -nrpo NAME,MOUNTPOINT "$DEVICE" | tail -n +2)

wipefs -a "$DEVICE"
printf 'label: gpt\n, , L\n' | sfdisk --wipe always "$DEVICE"
udevadm settle

PARTITION="$(lsblk -nrpo NAME,TYPE "$DEVICE" | awk '$2=="part" {print $1; exit}')"
[[ -b "$PARTITION" ]] || { echo "Partition was not created on $DEVICE" >&2; exit 1; }

mkfs.ext4 -F -m 0 -L "$LABEL" "$PARTITION"
UUID="$(blkid -s UUID -o value "$PARTITION")"
[[ -n "$UUID" ]] || { echo "Unable to read filesystem UUID" >&2; exit 1; }

mkdir -p "$MOUNTPOINT"
chown root:root "$MOUNTPOINT"
chmod 0555 "$MOUNTPOINT"

cp -a /etc/fstab "/etc/fstab.wvc-before-nvme.$(date +%Y%m%d-%H%M%S)"
python3 - "$MOUNTPOINT" "$UUID" <<'PY'
from pathlib import Path
import sys

mountpoint, uuid = sys.argv[1:]
path = Path('/etc/fstab')
lines = path.read_text(encoding='utf-8').splitlines()
kept = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        kept.append(line)
        continue
    fields = stripped.split()
    if len(fields) >= 2 and fields[1] == mountpoint:
        continue
    kept.append(line)
kept.append(f'UUID={uuid} {mountpoint} ext4 defaults,noatime,nofail,x-systemd.device-timeout=10s 0 2')
path.write_text('\n'.join(kept) + '\n', encoding='utf-8')
PY

mount "$MOUNTPOINT"
mountpoint -q "$MOUNTPOINT" || { echo "$MOUNTPOINT is not mounted" >&2; exit 1; }
[[ "$(findmnt -n -o FSTYPE "$MOUNTPOINT")" == "ext4" ]] || { echo "Unexpected filesystem" >&2; exit 1; }

install -d -o wentylacja -g wentylacja -m 0750 "$MOUNTPOINT/workshop-ventilation"
install -d -o wentylacja -g wentylacja -m 0700 "$MOUNTPOINT/wvc-service-heartbeat"
install -d -o wentylacja -g wentylacja -m 0750 "$MOUNTPOINT/zigbee2mqtt"

systemctl enable --now fstrim.timer >/dev/null

echo
echo "===== NVME DATA DISK READY ====="
findmnt "$MOUNTPOINT"
df -hT "$MOUNTPOINT"
echo "UUID=$UUID"
echo "Next step: sudo ./tools/migrate_cm5_persistent_data_to_nvme.sh --apply"
