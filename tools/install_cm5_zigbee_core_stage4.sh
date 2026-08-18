#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SOURCE="${ROOT_DIR}/deploy/systemd/ventilation-core.service"
UNIT_TARGET="/etc/systemd/system/ventilation-core.service"
ALLOW_HARDWARE_OFFLINE=false

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

section() {
    printf '\n===== %s =====\n' "$1"
}

usage() {
    cat <<'EOF'
Usage:
  sudo bash tools/install_cm5_zigbee_core_stage4.sh
  sudo bash tools/install_cm5_zigbee_core_stage4.sh --allow-hardware-offline

--allow-hardware-offline
  Use only when the execution hardware is intentionally disconnected and the
  CM5 is being validated standalone. The script still requires software
  setpoints 0 V / 0 V, permit_join=false and a DAC_COMMUNICATION_LOST fault.
  Normal production deployment remains strict and requires confirmed STOP,
  hardware_ready=true and output_state_known=true.
EOF
}

if [[ "${1:-}" == "--allow-hardware-offline" ]]; then
    ALLOW_HARDWARE_OFFLINE=true
    shift
fi
if [[ "$#" -ne 0 ]]; then
    usage >&2
    exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root: sudo bash tools/install_cm5_zigbee_core_stage4.sh [--allow-hardware-offline]"
fi

section "DEPLOYMENT MODE"
if [[ "${ALLOW_HARDWARE_OFFLINE}" == true ]]; then
    echo "hardware mode: intentionally offline / standalone CM5"
    echo "safety rule: software setpoints must remain 0 V / 0 V"
else
    echo "hardware mode: normal strict validation"
fi

section "PRECHECK SERVICES"
for unit in ventilation-core.service mosquitto.service zigbee2mqtt.service; do
    if systemctl is-active --quiet "${unit}"; then
        echo "${unit}: active"
    else
        fail "${unit} is not active"
    fi
done

section "PRECHECK SAFE STATE"
status_file="$(mktemp)"
trap 'rm -f "${status_file:-}" "${bridge_file:-}"' EXIT
if ! PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${status_file}"; then
    cat "${status_file}" >&2 || true
    fail "Unable to read ventilation-core status"
fi
python3 - "${status_file}" "${ALLOW_HARDWARE_OFFLINE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
allow_hardware_offline = sys.argv[2].lower() == "true"
if payload.get("ok") is not True:
    raise SystemExit("ERROR: ventilation-core status is not OK")
state = payload["state"]
setpoints = state["setpoints"]
if float(setpoints.get("supply_voltage", -1)) != 0.0 or float(setpoints.get("extract_voltage", -1)) != 0.0:
    raise SystemExit(f"ERROR: expected software setpoints 0 V / 0 V before Stage 4 deployment, got {setpoints!r}")

if state.get("mode") == "STOP" and state.get("hardware_ready") is True and state.get("output_state_known") is True:
    print("STOP / 0 V: PASS")
    print("hardware_ready: True")
    print("output_state_known: True")
elif allow_hardware_offline:
    alarms = state.get("active_alarms") or []
    dac_fault = any(alarm.get("code") == "DAC_COMMUNICATION_LOST" for alarm in alarms)
    if state.get("mode") != "FAULT":
        raise SystemExit(f"ERROR: offline-hardware mode expected FAULT from disconnected DAC, got {state.get('mode')!r}")
    if state.get("hardware_ready") is not False or state.get("output_state_known") is not False:
        raise SystemExit("ERROR: offline-hardware mode expected hardware_ready=false and output_state_known=false")
    if not dac_fault:
        raise SystemExit("ERROR: offline-hardware mode requires active DAC_COMMUNICATION_LOST fault")
    print("standalone CM5 / hardware intentionally offline: PASS")
    print("software setpoints: 0 V / 0 V")
    print("expected DAC_COMMUNICATION_LOST fault: present")
else:
    raise SystemExit(
        "ERROR: hardware state is not confirmed safe; if execution hardware is intentionally disconnected, "
        "rerun with --allow-hardware-offline"
    )
PY

section "PRECHECK ZIGBEE CLOSED"
bridge_file="$(mktemp)"
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/bridge/info' -C 1 -W 5 >"${bridge_file}" \
    || fail "Unable to read retained zigbee2mqtt/bridge/info"
python3 - "${bridge_file}" <<'PY'
import json
import sys
from pathlib import Path

info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if info.get("permit_join") is not False:
    raise SystemExit(f"ERROR: permit_join must be false before deployment, got {info.get('permit_join')!r}")
coordinator = info.get("coordinator") or {}
print("permit_join: false")
print("coordinator:", coordinator.get("type"))
print("coordinator ieee:", coordinator.get("ieee_address"))
PY

section "PYTHON MQTT RUNTIME"
apt-get update
apt-get install -y python3-paho-mqtt
python3 - <<'PY'
from importlib.metadata import version
import paho.mqtt.client as mqtt

print("paho-mqtt:", version("paho-mqtt"))
print("callback API:", mqtt.CallbackAPIVersion.VERSION2)
PY

section "STATIC VALIDATION"
PYTHONPATH="${ROOT_DIR}/src" python3 -m compileall -q "${ROOT_DIR}/src"
PYTHONPATH="${ROOT_DIR}/src" python3 -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_zigbee_core_stage4.py' -v

section "INSTALL CORE UNIT"
[[ -f "${UNIT_SOURCE}" ]] || fail "Missing ${UNIT_SOURCE}"
install -m 0644 "${UNIT_SOURCE}" "${UNIT_TARGET}"
systemctl daemon-reload

section "RESTART CORE"
systemctl restart ventilation-core.service
for _ in $(seq 1 20); do
    if systemctl is-active --quiet ventilation-core.service; then
        break
    fi
    sleep 0.5
done
if ! systemctl is-active --quiet ventilation-core.service; then
    journalctl -u ventilation-core.service -n 120 --no-pager >&2 || true
    fail "ventilation-core.service failed after Stage 4 deployment"
fi
echo "ventilation-core.service: active"

section "WAIT FOR CORE MQTT CONNECTION"
connected=false
for _ in $(seq 1 20); do
    if PYTHONPATH="${ROOT_DIR}/src" python3 -m ventilation_core.ctl status >"${status_file}" 2>/dev/null; then
        if python3 - "${status_file}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
zigbee = (payload.get("state") or {}).get("zigbee")
raise SystemExit(0 if zigbee and zigbee.get("running") is True and zigbee.get("connected") is True else 1)
PY
        then
            connected=true
            break
        fi
    fi
    sleep 0.5
done

if [[ "${connected}" != true ]]; then
    cat "${status_file}" >&2 || true
    journalctl -u ventilation-core.service -n 120 --no-pager >&2 || true
    fail "ventilation-core did not connect to local Zigbee MQTT broker"
fi

section "CORE ZIGBEE STATE"
python3 - "${status_file}" "${ALLOW_HARDWARE_OFFLINE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
allow_hardware_offline = sys.argv[2].lower() == "true"
state = payload["state"]
zigbee = state["zigbee"]
expected = {
    "supply": ("temp_nawiew", "0xa4c13810e66fffff"),
    "extract": ("temp_wywiew", "0xa4c13810bdedffff"),
}
seen = {}
for device in zigbee["devices"]:
    seen[device["role"]] = (device["friendly_name"], device["ieee_address"])
if seen != expected:
    raise SystemExit(f"ERROR: unexpected Zigbee device mapping: {seen!r}")

print("mqtt connected:", zigbee["connected"])
for device in zigbee["devices"]:
    print(
        f"{device['role']}: {device['friendly_name']} "
        f"ieee={device['ieee_address']} "
        f"temperature={device['temperature_celsius']} "
        f"battery={device['battery_percent']} "
        f"available={device['available']}"
    )

setpoints = state["setpoints"]
if float(setpoints["supply_voltage"]) != 0.0 or float(setpoints["extract_voltage"]) != 0.0:
    raise SystemExit(f"ERROR: software setpoints are not 0 V after deployment: {setpoints!r}")

if allow_hardware_offline:
    alarms = state.get("active_alarms") or []
    dac_fault = any(alarm.get("code") == "DAC_COMMUNICATION_LOST" for alarm in alarms)
    if state.get("mode") != "FAULT" or not dac_fault:
        raise SystemExit(
            f"ERROR: expected disconnected-DAC FAULT after standalone deployment, got mode={state.get('mode')!r}"
        )
    print("post-deploy standalone CM5 / hardware offline: PASS")
    print("software setpoints: 0 V / 0 V")
else:
    if state.get("mode") != "STOP":
        raise SystemExit(f"ERROR: core mode changed during deployment: {state.get('mode')!r}")
    if state.get("hardware_ready") is not True or state.get("output_state_known") is not True:
        raise SystemExit("ERROR: hardware state is not confirmed safe after deployment")
    print("post-deploy STOP / 0 V: PASS")
PY

section "REGRESSION CHECK"
for unit in ventilation-core.service wvc-web-ui.service mosquitto.service zigbee2mqtt.service; do
    printf '%-28s %s\n' "${unit}" "$(systemctl is-active "${unit}" 2>/dev/null || true)"
done

echo
echo "Stage 4 PASS: ventilation-core owns read-only Zigbee MQTT telemetry for temp_nawiew and temp_wywiew."
if [[ "${ALLOW_HARDWARE_OFFLINE}" == true ]]; then
    echo "Validation mode: standalone CM5 with execution hardware intentionally offline."
fi
echo "No Zigbee control, pairing UI or alert changes were introduced."
