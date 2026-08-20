#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/wentylacja/workshop-ventilation-controller"
DATA_ROOT="/srv/wvc-data"
WEB_ENV_FILE="/etc/default/wvc-web-ui"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

if mountpoint -q "$DATA_ROOT"; then
  pass "$DATA_ROOT is a mountpoint"
else
  fail "$DATA_ROOT is not mounted"
fi

SOURCE="$(findmnt -n -o SOURCE "$DATA_ROOT" 2>/dev/null || true)"
FSTYPE="$(findmnt -n -o FSTYPE "$DATA_ROOT" 2>/dev/null || true)"
[[ "$SOURCE" == /dev/nvme* ]] && pass "data tier is NVMe ($SOURCE)" || fail "data tier source is $SOURCE"
[[ "$FSTYPE" == ext4 ]] && pass "data tier filesystem is ext4" || fail "filesystem is $FSTYPE"

ROOT_SOURCE="$(findmnt -n -o SOURCE /)"
[[ "$ROOT_SOURCE" == /dev/mmcblk* ]] && pass "OS root remains on eMMC ($ROOT_SOURCE)" || fail "unexpected root source: $ROOT_SOURCE"

for path in \
  "$DATA_ROOT/workshop-ventilation" \
  "$DATA_ROOT/wvc-service-heartbeat" \
  "$DATA_ROOT/zigbee2mqtt"; do
  [[ -d "$path" ]] && pass "directory exists: $path" || fail "missing directory: $path"
done

check_unit_contains() {
  local unit="$1" fragment="$2"
  if systemctl cat "$unit" 2>/dev/null | grep -Fq -- "$fragment"; then
    pass "$unit -> $fragment"
  else
    fail "$unit missing: $fragment"
  fi
}

check_env_file_value() {
  local file="$1" key="$2" expected="$3" line actual
  [[ -f "$file" ]] || {
    pass "$file absent; WebGUI unit defaults remain authoritative"
    return
  }

  line="$(
    grep -E "^[[:space:]]*${key}=" "$file" 2>/dev/null \
      | tail -n 1 || true
  )"
  if [[ -z "$line" ]]; then
    pass "$file does not override $key; WebGUI unit value remains authoritative"
    return
  fi

  actual="${line#*=}"
  if [[ "$actual" == "$expected" ]]; then
    pass "$file -> $key=$expected"
  else
    fail "$file overrides $key with '$actual' (expected $expected)"
  fi
}

check_process_env_value() {
  local env_text="$1" key="$2" expected="$3" actual
  actual="$(
    printf '%s\n' "$env_text" \
      | grep -E "^${key}=" \
      | tail -n 1 \
      | cut -d= -f2- || true
  )"
  if [[ "$actual" == "$expected" ]]; then
    pass "wvc-web-ui effective env -> $key=$expected"
  else
    fail "wvc-web-ui effective env has $key='${actual:-<missing>}' (expected $expected)"
  fi
}

check_unit_contains ventilation-core.service "/srv/wvc-data/workshop-ventilation/alerts.sqlite3"
check_unit_contains ventilation-core.service "WVC_ALERT_STORE_ALLOW_VOLATILE_FALLBACK=1"
check_unit_contains wvc-telemetry-sync.service "/srv/wvc-data/workshop-ventilation/telemetry.sqlite3"
check_unit_contains wvc-ai-advisory.service "/srv/wvc-data/workshop-ventilation/ai-advisory.json"
check_unit_contains wvc-weather.service "/srv/wvc-data/workshop-ventilation/weather.json"
check_unit_contains wvc-service-agent.service "/srv/wvc-data/wvc-service-heartbeat"
check_unit_contains zigbee2mqtt.service "ZIGBEE2MQTT_DATA=/srv/wvc-data/zigbee2mqtt"

for unit in wvc-telemetry-sync.service wvc-ai-advisory.service wvc-weather.service wvc-service-agent.service zigbee2mqtt.service; do
  check_unit_contains "$unit" "ExecStartPre=/usr/bin/mountpoint -q /srv/wvc-data"
done

declare -A WEB_DATA_PATHS=(
  [WVC_WEB_TELEMETRY_DATABASE]="$DATA_ROOT/workshop-ventilation/telemetry.sqlite3"
  [WVC_WEB_ALERT_DATABASE]="$DATA_ROOT/workshop-ventilation/alerts.sqlite3"
  [WVC_WEB_WEATHER_SNAPSHOT]="$DATA_ROOT/workshop-ventilation/weather.json"
  [WVC_WEB_AI_ADVISORY_CACHE]="$DATA_ROOT/workshop-ventilation/ai-advisory.json"
)
for key in WVC_WEB_TELEMETRY_DATABASE WVC_WEB_ALERT_DATABASE WVC_WEB_WEATHER_SNAPSHOT WVC_WEB_AI_ADVISORY_CACHE; do
  check_env_file_value "$WEB_ENV_FILE" "$key" "${WEB_DATA_PATHS[$key]}"
done

WEB_PID="$(systemctl show -p MainPID --value wvc-web-ui.service 2>/dev/null || true)"
if [[ "$WEB_PID" =~ ^[0-9]+$ ]] && (( WEB_PID > 0 )) && [[ -r "/proc/$WEB_PID/environ" ]]; then
  WEB_PROCESS_ENV="$(tr '\0' '\n' <"/proc/$WEB_PID/environ")"
  for key in WVC_WEB_TELEMETRY_DATABASE WVC_WEB_ALERT_DATABASE WVC_WEB_WEATHER_SNAPSHOT WVC_WEB_AI_ADVISORY_CACHE; do
    check_process_env_value "$WEB_PROCESS_ENV" "$key" "${WEB_DATA_PATHS[$key]}"
  done
else
  echo "INFO: wvc-web-ui.service is not running; effective WebGUI environment check skipped"
fi

if grep -Rqs '^Storage=volatile$' /etc/systemd/journald.conf.d; then
  pass "system journal is volatile; no persistent journal churn on eMMC"
else
  fail "journald volatile storage protection is not installed"
fi

if grep -Fq 'persistence false' /etc/mosquitto/conf.d/wvc-zigbee-local.conf 2>/dev/null; then
  pass "Mosquitto persistence is disabled"
else
  fail "Mosquitto persistence false not installed"
fi

if [[ -f "$DATA_ROOT/workshop-ventilation/telemetry.sqlite3" ]]; then
  pass "telemetry database exists on NVMe"
else
  fail "telemetry database missing on NVMe"
fi

if [[ -f "$DATA_ROOT/workshop-ventilation/alerts.sqlite3" ]]; then
  pass "alert history database exists on NVMe"
else
  echo "INFO: alerts.sqlite3 not present yet (acceptable if no persistent alert write has occurred)"
fi

if command -v vcgencmd >/dev/null; then
  echo "POWER: $(vcgencmd pmic_read_adc EXT5V_V 2>/dev/null || true)"
  THROTTLED="$(vcgencmd get_throttled 2>/dev/null || true)"
  echo "POWER: $THROTTLED"
  [[ "$THROTTLED" == "throttled=0x0" ]] && pass "no current/sticky throttling this boot" || fail "unexpected throttling state: $THROTTLED"
fi

if [[ -d "$ROOT" ]]; then
  cd "$ROOT"
  if PYTHONPATH=src python3 -m ventilation_core.ctl status >/tmp/wvc-nvme-core-status.json 2>/dev/null; then
    python3 - <<'PY'
import json
s=json.load(open('/tmp/wvc-nvme-core-status.json'))['state']
print('CORE mode=', s.get('mode'), 'hardware_ready=', s.get('hardware_ready'), 'output_state_known=', s.get('output_state_known'))
PY
    pass "core status API responds"
  else
    fail "core status API unavailable"
  fi
fi

echo
echo "===== DATA TIER ====="
df -hT "$DATA_ROOT" || true
du -sh "$DATA_ROOT"/* 2>/dev/null || true

echo
if (( FAIL )); then
  echo "NVME DATA TIER VALIDATION: FAIL" >&2
  exit 1
fi
echo "NVME DATA TIER VALIDATION: PASS"
