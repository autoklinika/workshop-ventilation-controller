#!/usr/bin/env bash
set -euo pipefail

# Temporary hardware-validation helper for PR #75.
# Downloads the exact CI artifact, verifies/copies the application image and,
# with --apply, performs OTA ONLY on sensor-node-2.

REPO="autoklinika/workshop-ventilation-controller"
ARTIFACT_ID="9441104052"
ARTIFACT_RUN_ID="32466929894"
ARTIFACT_HEAD_SHA="3fd613133240916994fdf7c419df270b1bc5190d"
ZIP_MEMBER="kamod_sen55_sensor_node.bin"
TARGET_IMAGE="/home/wentylacja/kamod_sen55_sensor_node_transport_diag.bin"
EXPECTED_SIZE="1006624"
EXPECTED_SHA256="97dab4b5944a21dba9950ea1318157da86fc77bc42223ac981b12ff98ce1df5f"
EXPECTED_FIRMWARE="0.6.1-stage1-transport-diag"
NODE_ID="sensor-node-2"
APPLY=0

usage() {
    cat <<'EOF'
Usage:
  bash install_kamod_transport_diag_node2.sh [--apply]

Without --apply the script downloads, verifies and copies the image, then
performs read-only service/OTA prechecks.

With --apply it additionally runs authenticated OTA ONLY on sensor-node-2 and
waits for completion.

GitHub artifact authentication is discovered in this order:
  1. GITHUB_TOKEN
  2. gh auth token
  3. git credential fill for github.com
  4. interactive token prompt

The token needs GitHub Actions read permission and is never printed.
EOF
}

while (($#)); do
    case "$1" in
        --apply) APPLY=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

for command in curl sha256sum stat od install git sudo systemctl python3; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "FAIL: missing required command: $command" >&2
        exit 1
    }
done

command -v wvc-servicectl >/dev/null 2>&1 || {
    echo "FAIL: wvc-servicectl is not installed/in PATH" >&2
    exit 1
}

WORKDIR="$(mktemp -d /tmp/wvc-kamod-diag-XXXXXX)"
ZIP_PATH="$WORKDIR/artifact.zip"
EXTRACT_DIR="$WORKDIR/extracted"
mkdir -p "$EXTRACT_DIR"
trap 'rm -rf "$WORKDIR"' EXIT

API_URL="https://api.github.com/repos/${REPO}/actions/artifacts/${ARTIFACT_ID}/zip"

header() {
    printf '\n===== %s =====\n' "$1"
}

valid_zip() {
    [[ -s "$ZIP_PATH" ]] || return 1
    python3 - "$ZIP_PATH" <<'PY'
import sys
import zipfile

path = sys.argv[1]
if not zipfile.is_zipfile(path):
    raise SystemExit(1)
with zipfile.ZipFile(path) as archive:
    bad = archive.testzip()
    if bad is not None:
        raise SystemExit(1)
PY
}

find_token() {
    local token=""

    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        printf '%s' "$GITHUB_TOKEN"
        return 0
    fi

    if command -v gh >/dev/null 2>&1; then
        token="$(gh auth token 2>/dev/null || true)"
        if [[ -n "$token" ]]; then
            printf '%s' "$token"
            return 0
        fi
    fi

    token="$(
        printf 'protocol=https\nhost=github.com\n\n' \
            | git credential fill 2>/dev/null \
            | sed -n 's/^password=//p' \
            | head -n1 \
            || true
    )"
    [[ -n "$token" ]] || return 1
    printf '%s' "$token"
}

download_artifact() {
    rm -f "$ZIP_PATH"

    # First try anonymous access. If GitHub refuses artifact download, retry
    # with locally available credentials without exposing the token.
    if curl \
        --fail --location --silent --show-error \
        --retry 2 --retry-delay 1 \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        "$API_URL" -o "$ZIP_PATH" 2>/dev/null && valid_zip; then
        echo "PASS: artifact downloaded anonymously"
        return 0
    fi

    rm -f "$ZIP_PATH"
    local token=""
    token="$(find_token || true)"

    if [[ -z "$token" && -t 0 ]]; then
        echo "GitHub requires authentication for this Actions artifact."
        read -r -s -p "GitHub token (Actions: read; Enter = abort): " token
        echo
    fi

    if [[ -z "$token" ]]; then
        echo "FAIL: no GitHub token available for Actions artifact download" >&2
        echo "Use GITHUB_TOKEN or authenticate GitHub CLI with: gh auth login" >&2
        return 1
    fi

    curl \
        --fail --location --silent --show-error \
        --retry 3 --retry-delay 1 \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        -H "Authorization: Bearer ${token}" \
        "$API_URL" -o "$ZIP_PATH"
    unset token

    valid_zip || {
        echo "FAIL: downloaded artifact is not a valid ZIP" >&2
        return 1
    }
    echo "PASS: artifact downloaded with local GitHub credentials"
}

header "SOURCE"
echo "repo:         $REPO"
echo "workflow run: $ARTIFACT_RUN_ID"
echo "artifact id:  $ARTIFACT_ID"
echo "source SHA:   $ARTIFACT_HEAD_SHA"
echo "target node:  $NODE_ID"

header "DOWNLOAD"
download_artifact

header "EXTRACT + VERIFY"
SOURCE_IMAGE="$EXTRACT_DIR/$ZIP_MEMBER"
python3 - "$ZIP_PATH" "$ZIP_MEMBER" "$SOURCE_IMAGE" <<'PY'
import pathlib
import sys
import zipfile

zip_path = sys.argv[1]
member = sys.argv[2]
out_path = pathlib.Path(sys.argv[3])
with zipfile.ZipFile(zip_path) as archive:
    names = archive.namelist()
    if member not in names:
        raise SystemExit(f"FAIL: artifact does not contain {member!r}")
    data = archive.read(member)
out_path.write_bytes(data)
PY

ACTUAL_SIZE="$(stat -c '%s' "$SOURCE_IMAGE")"
ACTUAL_SHA256="$(sha256sum "$SOURCE_IMAGE" | awk '{print $1}')"
FIRST_BYTE="$(od -An -tx1 -N1 "$SOURCE_IMAGE" | tr -d '[:space:]')"

echo "size:      $ACTUAL_SIZE"
echo "sha256:    $ACTUAL_SHA256"
echo "ESP magic: 0x$FIRST_BYTE"

[[ "$ACTUAL_SIZE" == "$EXPECTED_SIZE" ]] || {
    echo "FAIL: image size mismatch; expected $EXPECTED_SIZE" >&2
    exit 1
}
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || {
    echo "FAIL: image SHA-256 mismatch; expected $EXPECTED_SHA256" >&2
    exit 1
}
[[ "$FIRST_BYTE" == "e9" ]] || {
    echo "FAIL: ESP application magic is not 0xE9" >&2
    exit 1
}
echo "PASS: exact diagnostic application image verified"

header "COPY IMAGE"
install -m 0644 "$SOURCE_IMAGE" "$TARGET_IMAGE"
[[ "$(sha256sum "$TARGET_IMAGE" | awk '{print $1}')" == "$EXPECTED_SHA256" ]] || {
    echo "FAIL: copied image checksum mismatch" >&2
    exit 1
}
echo "PASS: copied to $TARGET_IMAGE"

header "SERVICE-PLANE PRECHECK"
[[ "$(systemctl is-enabled wvc-service-agent.service)" == "enabled" ]] || {
    echo "FAIL: wvc-service-agent.service is not enabled" >&2
    exit 1
}
[[ "$(systemctl is-active wvc-service-agent.service)" == "active" ]] || {
    echo "FAIL: wvc-service-agent.service is not active" >&2
    exit 1
}
echo "PASS: service agent enabled + active"

sudo -u wentylacja wvc-servicectl status | python3 -c '
import json, sys
node_id="sensor-node-2"
d=json.load(sys.stdin)
if d.get("ok") is not True: raise SystemExit("FAIL: service status ok != true")
if (d.get("agent") or {}).get("ready") is not True: raise SystemExit("FAIL: agent not ready")
if (d.get("network") or {}).get("ready") is not True: raise SystemExit("FAIL: service network not ready")
nodes={n.get("node_id"):n for n in d.get("nodes",[])}
n=nodes.get(node_id)
if not n: raise SystemExit("FAIL: sensor-node-2 not registered")
print("node-2 online:   ", n.get("online"))
print("node-2 address:  ", n.get("source_ip"))
print("node-2 firmware: ", n.get("firmware"))
print("node-2 sensor:   ", n.get("sensor_state"))
print("node-2 RS-485:   ", n.get("rs485_ready"))
print("node-2 Modbus:   ", n.get("modbus_monitor_ready"))
n1=nodes.get("sensor-node-1")
if n1: print("node-1 firmware: ", n1.get("firmware"))
'

header "CURRENT OTA STATUS"
sudo -u wentylacja wvc-servicectl ota-status "$NODE_ID"

if [[ $APPLY -eq 0 ]]; then
    header "READY"
    echo "Precheck PASS. Image ready at: $TARGET_IMAGE"
    echo "No OTA started. Re-run this helper with --apply."
    exit 0
fi

header "OTA INSTALL: SENSOR-NODE-2 ONLY"
echo "image:             $TARGET_IMAGE"
echo "sha256:            $EXPECTED_SHA256"
echo "expected firmware: $EXPECTED_FIRMWARE"

sudo -u wentylacja wvc-servicectl \
    ota-install "$NODE_ID" "$TARGET_IMAGE" --wait-timeout 300

header "POSTCHECK"
sudo -u wentylacja wvc-servicectl status | python3 -c '
import json, sys
expected="0.6.1-stage1-transport-diag"
d=json.load(sys.stdin)
nodes={n.get("node_id"):n for n in d.get("nodes",[])}
n=nodes.get("sensor-node-2")
if not n: raise SystemExit("FAIL: sensor-node-2 missing after OTA")
firmware=n.get("firmware")
print("node-2 online:    ", n.get("online"))
print("node-2 firmware:  ", firmware)
print("node-2 partition: ", n.get("ota_partition"))
print("node-2 pending:   ", n.get("ota_pending"))
print("node-2 RS-485:    ", n.get("rs485_ready"))
print("node-2 Modbus:    ", n.get("modbus_monitor_ready"))
n1=nodes.get("sensor-node-1")
if n1: print("node-1 firmware:  ", n1.get("firmware"))
if firmware != expected:
    raise SystemExit(f"FAIL: firmware {firmware!r} != {expected!r}")
if n.get("ota_pending") is not False:
    raise SystemExit("FAIL: diagnostic image still pending")
print("PASS: diagnostic firmware active and confirmed on sensor-node-2")
'

header "DONE"
echo "KAmod transport diagnostic OTA: PASS"
echo "sensor-node-2 -> $EXPECTED_FIRMWARE"
echo "sensor-node-1 was not targeted"
