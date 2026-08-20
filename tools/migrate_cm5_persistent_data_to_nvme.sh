#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/wentylacja/workshop-ventilation-controller"
DATA_ROOT="/srv/wvc-data"
WEB_ENV_FILE="/etc/default/wvc-web-ui"
WEB_ENV_BACKUP="/etc/default/wvc-web-ui.pre-nvme-migration.bak"
APPLY=0

usage() {
  cat <<'EOF'
Usage: sudo ./tools/migrate_cm5_persistent_data_to_nvme.sh [--apply]

Without --apply this script performs only preflight checks.
With --apply it safely stops WVC writers, copies existing persistent history to
/srv/wvc-data, installs the NVMe-aware systemd units, repairs existing WebGUI
data-path overrides in /etc/default/wvc-web-ui, and restores services.
Legacy source files remain on eMMC as a rollback snapshot and are not deleted.
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
[[ "$(findmnt -n -o FSTYPE "$DATA_ROOT")" == "ext4" ]] || { echo "$DATA_ROOT is not ext4" >&2; exit 1; }
SOURCE="$(findmnt -n -o SOURCE "$DATA_ROOT")"
[[ "$SOURCE" == /dev/nvme* ]] || { echo "$DATA_ROOT is not backed by NVMe: $SOURCE" >&2; exit 1; }

cd "$ROOT"

echo "===== NVME MIGRATION PREFLIGHT ====="
echo "repo HEAD:  $(git rev-parse HEAD)"
echo "data source: $SOURCE"
findmnt "$DATA_ROOT"

if (( ! APPLY )); then
  echo
  echo "PRECHECK PASS. No data changed. Re-run with --apply to perform migration."
  exit 0
fi
[[ $EUID -eq 0 ]] || { echo "--apply requires root (use sudo)." >&2; exit 1; }

# Force a safe control baseline before stopping the core.
PYTHONPATH="$ROOT/src" /usr/bin/python3 -m ventilation_core.ctl stop >/dev/null
PYTHONPATH="$ROOT/src" /usr/bin/python3 -m ventilation_core.ctl status | /usr/bin/python3 -c '
import json,sys
s=json.load(sys.stdin)["state"]
if s.get("mode") != "STOP": raise SystemExit("core is not in STOP")
sp=s.get("setpoints", {})
if float(sp.get("supply_voltage", 0)) != 0 or float(sp.get("extract_voltage", 0)) != 0:
    raise SystemExit("fan outputs are not 0 V")
print("safe baseline: STOP / 0 V")
'

UNITS=(
  ventilation-core.service
  wvc-telemetry-sync.service
  wvc-ai-advisory.service
  wvc-weather.service
  wvc-web-ui.service
  wvc-service-agent.service
  wvc-service-heartbeat.service
  zigbee2mqtt.service
)
declare -A WAS_ACTIVE
for unit in "${UNITS[@]}"; do
  if systemctl is-active --quiet "$unit"; then WAS_ACTIVE["$unit"]=1; else WAS_ACTIVE["$unit"]=0; fi
done

restore_services() {
  local unit
  for unit in mosquitto.service zigbee2mqtt.service wvc-service-agent.service wvc-service-heartbeat.service ventilation-core.service wvc-telemetry-sync.service wvc-ai-advisory.service wvc-weather.service wvc-web-ui.service; do
    if [[ "${WAS_ACTIVE[$unit]:-0}" == "1" ]]; then
      systemctl start "$unit" || true
    fi
  done
}
trap restore_services ERR

# Stop readers/writers first, core last. All SQLite copies are then quiescent.
systemctl stop wvc-telemetry-sync.service wvc-ai-advisory.service wvc-weather.service wvc-web-ui.service || true
systemctl stop wvc-service-agent.service wvc-service-heartbeat.service zigbee2mqtt.service || true
systemctl stop ventilation-core.service

install -d -o wentylacja -g wentylacja -m 0750 "$DATA_ROOT/workshop-ventilation"
install -d -o wentylacja -g wentylacja -m 0700 "$DATA_ROOT/wvc-service-heartbeat"
install -d -o wentylacja -g wentylacja -m 0750 "$DATA_ROOT/zigbee2mqtt"

copy_if_exists() {
  local source="$1" destination="$2"
  if [[ -e "$source" ]]; then
    cp -a "$source" "$destination"
    echo "copied: $source -> $destination"
  fi
}

upsert_env_value() {
  local file="$1" key="$2" value="$3" tmp
  [[ -f "$file" ]] || return 0

  tmp="$(mktemp "${file}.tmp.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $0 ~ "^[[:space:]]*" key "=" {
      if (!found) {
        print key "=" value
        found=1
      }
      next
    }
    { print }
    END {
      if (!found) print key "=" value
    }
  ' "$file" >"$tmp"

  chown --reference="$file" "$tmp"
  chmod --reference="$file" "$tmp"
  mv -f "$tmp" "$file"
}

for name in alerts.sqlite3 alerts.sqlite3-wal alerts.sqlite3-shm telemetry.sqlite3 telemetry.sqlite3-wal telemetry.sqlite3-shm ai-advisory.json weather.json; do
  copy_if_exists "/var/lib/workshop-ventilation/$name" "$DATA_ROOT/workshop-ventilation/"
done

if [[ -d /var/lib/wvc-service-heartbeat ]]; then
  cp -a /var/lib/wvc-service-heartbeat/. "$DATA_ROOT/wvc-service-heartbeat/"
  echo "copied: /var/lib/wvc-service-heartbeat -> $DATA_ROOT/wvc-service-heartbeat"
fi
if [[ -d /var/lib/zigbee2mqtt ]]; then
  cp -a /var/lib/zigbee2mqtt/. "$DATA_ROOT/zigbee2mqtt/"
  echo "copied: /var/lib/zigbee2mqtt -> $DATA_ROOT/zigbee2mqtt"
fi

chown -R wentylacja:wentylacja "$DATA_ROOT/workshop-ventilation" "$DATA_ROOT/wvc-service-heartbeat" "$DATA_ROOT/zigbee2mqtt"
chmod 0750 "$DATA_ROOT/workshop-ventilation" "$DATA_ROOT/zigbee2mqtt"
chmod 0700 "$DATA_ROOT/wvc-service-heartbeat"

# Install only deployment artifacts; application source remains the checked-out branch.
for unit in ventilation-core.service wvc-telemetry-sync.service wvc-ai-advisory.service wvc-weather.service wvc-web-ui.service wvc-service-agent.service wvc-service-heartbeat.service zigbee2mqtt.service; do
  install -m 0644 "$ROOT/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
install -m 0644 "$ROOT/deploy/cm5/zigbee/mosquitto/wvc-zigbee-local.conf" /etc/mosquitto/conf.d/wvc-zigbee-local.conf
install -d -m 0755 /etc/systemd/journald.conf.d
install -m 0644 "$ROOT/deploy/cm5/storage/90-wvc-emmc-protection.conf" /etc/systemd/journald.conf.d/90-wvc-emmc-protection.conf

# EnvironmentFile is loaded after Environment= entries in the WebGUI unit, so
# an old /etc/default/wvc-web-ui can silently override the NVMe paths. Preserve
# the site's host/port/zone settings and repair only the four data-path keys.
if [[ -f "$WEB_ENV_FILE" ]]; then
  if [[ ! -e "$WEB_ENV_BACKUP" ]]; then
    cp -a "$WEB_ENV_FILE" "$WEB_ENV_BACKUP"
    echo "backup: $WEB_ENV_FILE -> $WEB_ENV_BACKUP"
  fi
  upsert_env_value "$WEB_ENV_FILE" "WVC_WEB_TELEMETRY_DATABASE" "$DATA_ROOT/workshop-ventilation/telemetry.sqlite3"
  upsert_env_value "$WEB_ENV_FILE" "WVC_WEB_ALERT_DATABASE" "$DATA_ROOT/workshop-ventilation/alerts.sqlite3"
  upsert_env_value "$WEB_ENV_FILE" "WVC_WEB_WEATHER_SNAPSHOT" "$DATA_ROOT/workshop-ventilation/weather.json"
  upsert_env_value "$WEB_ENV_FILE" "WVC_WEB_AI_ADVISORY_CACHE" "$DATA_ROOT/workshop-ventilation/ai-advisory.json"
  echo "updated WebGUI data-path overrides in $WEB_ENV_FILE"
fi

systemctl daemon-reload
systemctl restart systemd-journald
systemctl restart mosquitto.service

# Restore only services that were active before migration.
for unit in zigbee2mqtt.service wvc-service-agent.service wvc-service-heartbeat.service ventilation-core.service wvc-telemetry-sync.service wvc-ai-advisory.service wvc-weather.service wvc-web-ui.service; do
  if [[ "${WAS_ACTIVE[$unit]}" == "1" ]]; then
    systemctl start "$unit"
  fi
done
trap - ERR

sleep 3

echo
echo "===== POST-MIGRATION ====="
findmnt "$DATA_ROOT"
for unit in ventilation-core.service wvc-telemetry-sync.service wvc-ai-advisory.service wvc-weather.service wvc-web-ui.service wvc-service-agent.service zigbee2mqtt.service; do
  printf '%-32s ' "$unit"
  systemctl is-active "$unit" || true
done

echo
echo "Legacy eMMC files were intentionally retained and are now rollback snapshots."
echo "Run: sudo ./tools/validate_cm5_nvme_data.sh"
