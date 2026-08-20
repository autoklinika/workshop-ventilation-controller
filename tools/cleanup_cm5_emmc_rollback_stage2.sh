#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/wentylacja/workshop-ventilation-controller"
DATA_ROOT="/srv/wvc-data"
USER_HOME="/home/wentylacja"
VSCODE_LINK="$USER_HOME/.vscode-server"
VSCODE_TARGET="$DATA_ROOT/development/vscode-server"
ARCHIVE_ROOT="$DATA_ROOT/rollback/emmc-stage1-20260820"
APPLY=0

usage() {
  cat <<'EOF'
Usage: sudo ./tools/cleanup_cm5_emmc_rollback_stage2.sh [--apply]

Without --apply the script performs read-only checks and prints what would be
removed from eMMC.

With --apply it:
  * requires the NVMe data tier and Stage 2 VS Code relocation to be healthy,
  * refuses to continue if any process still has a descriptor open in a
    .vscode-server.emmc-rollback-* directory,
  * copies legacy WVC Stage 1 rollback data from eMMC to an NVMe archive,
  * verifies copied files/directories before deleting their eMMC originals,
  * deletes obsolete VS Code rollback directories from eMMC,
  * NEVER removes automation.sqlite3 or zigbee-roles.json.

The ventilation-core service is not stopped or restarted.
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
DATA_SOURCE="$(findmnt -n -o SOURCE "$DATA_ROOT")"
ROOT_SOURCE="$(findmnt -n -o SOURCE /)"
[[ "$DATA_SOURCE" == /dev/nvme* ]] || { echo "$DATA_ROOT is not backed by NVMe: $DATA_SOURCE" >&2; exit 1; }
[[ "$ROOT_SOURCE" == /dev/mmcblk* ]] || { echo "/ is not backed by eMMC: $ROOT_SOURCE" >&2; exit 1; }

EXPECTED_TARGET="$(readlink -f "$VSCODE_TARGET" 2>/dev/null || true)"
CURRENT_TARGET="$(readlink -f "$VSCODE_LINK" 2>/dev/null || true)"
[[ -L "$VSCODE_LINK" ]] || { echo "$VSCODE_LINK is not a symlink" >&2; exit 1; }
[[ -n "$EXPECTED_TARGET" && "$CURRENT_TARGET" == "$EXPECTED_TARGET" ]] || {
  echo "VS Code link does not resolve to expected NVMe target" >&2
  echo "current:  $CURRENT_TARGET" >&2
  echo "expected: $EXPECTED_TARGET" >&2
  exit 1
}
[[ "$(findmnt -n -o SOURCE -T "$VSCODE_TARGET")" == /dev/nvme* ]] || {
  echo "VS Code target is not backed by NVMe" >&2
  exit 1
}

open_rollback_fds=0
while IFS= read -r fd; do
  target="$(readlink "$fd" 2>/dev/null || true)"
  if [[ "$target" == "$USER_HOME/.vscode-server.emmc-rollback-"* ]]; then
    echo "OPEN FD: $fd -> $target" >&2
    open_rollback_fds=1
  fi
done < <(find /proc/[0-9]*/fd -type l 2>/dev/null || true)
[[ $open_rollback_fds -eq 0 ]] || {
  echo "REFUSING: VS Code rollback data is still open by a process" >&2
  exit 1
}

mapfile -t VSCODE_ROLLBACKS < <(
  find "$USER_HOME" -maxdepth 1 -mindepth 1 -type d \
    -name '.vscode-server.emmc-rollback-*' -print | sort
)

WVC_FILES=()
for pattern in \
  '/var/lib/workshop-ventilation/alerts.sqlite3'* \
  '/var/lib/workshop-ventilation/telemetry.sqlite3'* \
  '/var/lib/workshop-ventilation/ai-advisory.json' \
  '/var/lib/workshop-ventilation/weather.json'
do
  for path in $pattern; do
    [[ -e "$path" ]] && WVC_FILES+=("$path")
  done
done

WVC_DIRS=()
for path in /var/lib/wvc-service-heartbeat /var/lib/zigbee2mqtt; do
  [[ -d "$path" ]] && WVC_DIRS+=("$path")
done

# Guard rails: these operational low-write configuration paths must remain.
[[ -e /var/lib/workshop-ventilation/automation.sqlite3 ]] || {
  echo "WARNING: automation.sqlite3 not found; cleanup will not create or remove it" >&2
}
[[ -e /var/lib/workshop-ventilation/zigbee-roles.json ]] || {
  echo "WARNING: zigbee-roles.json not found; cleanup will not create or remove it" >&2
}

echo "===== EMMC ROLLBACK CLEANUP STAGE 2 ====="
echo "root source:   $ROOT_SOURCE"
echo "data source:   $DATA_SOURCE"
echo "archive:       $ARCHIVE_ROOT"
echo

echo "===== VS CODE ROLLBACKS ON EMMC ====="
if ((${#VSCODE_ROLLBACKS[@]})); then
  for path in "${VSCODE_ROLLBACKS[@]}"; do du -sh "$path"; done
else
  echo "NONE"
fi

echo
echo "===== WVC LEGACY FILES ON EMMC ====="
if ((${#WVC_FILES[@]})); then
  for path in "${WVC_FILES[@]}"; do ls -lh "$path"; done
else
  echo "NONE"
fi

echo
echo "===== WVC LEGACY DIRECTORIES ON EMMC ====="
if ((${#WVC_DIRS[@]})); then
  for path in "${WVC_DIRS[@]}"; do du -sh "$path"; done
else
  echo "NONE"
fi

echo
echo "===== MUST REMAIN ON EMMC ====="
ls -lh /var/lib/workshop-ventilation/automation.sqlite3* 2>/dev/null || true
ls -lh /var/lib/workshop-ventilation/zigbee-roles.json 2>/dev/null || true

echo
echo "===== SPACE BEFORE ====="
df -hT / "$DATA_ROOT"

if (( ! APPLY )); then
  echo
  echo "PRECHECK PASS. No data changed. Re-run with --apply to archive and clean rollback data."
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "--apply requires root (use sudo)" >&2; exit 1; }

install -d -o wentylacja -g wentylacja -m 0750 "$ARCHIVE_ROOT"

archive_and_verify_file() {
  local src="$1"
  local dst="$ARCHIVE_ROOT$src"
  install -d -o wentylacja -g wentylacja -m 0750 "$(dirname "$dst")"
  cp -a "$src" "$dst"
  cmp -s "$src" "$dst" || {
    echo "VERIFY FAILED: $src -> $dst" >&2
    exit 1
  }
  rm -f "$src"
  echo "archived+removed: $src"
}

archive_and_verify_dir() {
  local src="$1"
  local dst="$ARCHIVE_ROOT$src"
  install -d -o wentylacja -g wentylacja -m 0750 "$(dirname "$dst")"
  rm -rf "$dst"
  cp -a "$src" "$dst"
  diff -qr "$src" "$dst" >/dev/null || {
    echo "VERIFY FAILED: $src -> $dst" >&2
    exit 1
  }
  rm -rf "$src"
  echo "archived+removed: $src"
}

for path in "${WVC_FILES[@]}"; do archive_and_verify_file "$path"; done
for path in "${WVC_DIRS[@]}"; do archive_and_verify_dir "$path"; done

for path in "${VSCODE_ROLLBACKS[@]}"; do
  rm -rf "$path"
  echo "removed obsolete VS Code rollback: $path"
done

# Archive integrity manifest (NVMe only).
(
  cd "$ARCHIVE_ROOT"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 -r sha256sum > SHA256SUMS
)
chown -R wentylacja:wentylacja "$ARCHIVE_ROOT"
sync

# Final guard rails.
[[ -e /var/lib/workshop-ventilation/automation.sqlite3 ]] || {
  echo "FATAL: automation.sqlite3 missing after cleanup" >&2
  exit 1
}
[[ -e /var/lib/workshop-ventilation/zigbee-roles.json ]] || {
  echo "FATAL: zigbee-roles.json missing after cleanup" >&2
  exit 1
}
[[ -L "$VSCODE_LINK" && "$(readlink -f "$VSCODE_LINK")" == "$EXPECTED_TARGET" ]] || {
  echo "FATAL: VS Code symlink changed unexpectedly" >&2
  exit 1
}

echo
echo "===== CLEANUP COMPLETE ====="
echo "NVMe rollback archive: $ARCHIVE_ROOT"
echo "Archive manifest:      $ARCHIVE_ROOT/SHA256SUMS"
echo
echo "===== SPACE AFTER ====="
df -hT / "$DATA_ROOT"

echo
echo "Run validators:"
echo "  sudo ./tools/validate_cm5_nvme_data.sh"
echo "  sudo ./tools/validate_cm5_emmc_write_hardening_stage2.sh"
