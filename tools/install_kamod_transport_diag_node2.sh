#!/usr/bin/env bash
set -euo pipefail

# Temporary hardware-validation helper for PR #75.
# Downloads the exact CI artifact, verifies the application image, copies it
# into /home/wentylacja, and (with --apply) performs OTA ONLY on sensor-node-2.

REPO="autoklinika/workshop-ventilation-controller"
ARTIFACT_ID="9441104052"
ARTIFACT_RUN_ID="32466929894"
ARTIFACT_HEAD_SHA="3fd613133240916994fdf7c419df270b1bc5190d"
ARTIFACT_NAME="kamod-service-ota-bootstrap-f521b9ca072de3066011bf07c94e81bb12b696d7"
ZIP_MEMBER="kamod_sen55_sensor_node.bin"
TARGET_IMAGE="/home/wentylacja/kamod_sen55_sensor_node_transport_diag.bin"
EXPECTED_SIZE="1006624"
EXPECTED_SHA256="97dab4b5944a21dba9950ea1318157da86fc77bc42223ac981b12ff98ce1df5f"
EXPECTED_FIRMWARE="0.6.1-stage1-transport-diag"
NODE_ID="sensor-node-2"
BRANCH="agent/kamod-heartbeat-transport-diagnostics-v2"
APPLY=0

usage() {
    cat <<'EOF'
Usage:
  bash tools/install_kamod_transport_diag_node2.sh [--apply]

Without --apply:
  - downloads the exact GitHub Actions artifact,
  - verifies ZIP/member/image SHA-256 and size,
  - copies the image to /home/wentylacja,
  - performs read-only service-plane / OTA prechecks.

With --apply:
  - performs all of the above,
  - executes authenticated OTA ONLY for sensor-node-2,
  - waits for OTA completion and prints final node state.

GitHub artifact authentication is discovered automatically in this order:
  1. GITHUB_TOKEN environment variable,
  2. `gh auth token`,
  3. `git credential fill` for github.com,
  4. interactive token prompt if running in a terminal.

The token needs GitHub Actions read permission. The token is never printed.
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

for command in curl unzip sha256sum stat python3 git sudo; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "FAIL: missing required command: $command" >&2
        exit 1
    }
done

if ! command -v wvc-servicectl >/dev/null 2>&1; then
    echo "FAIL: wvc-servicectl is not installed/in PATH" >&2
    exit 1
fi

WORKDIR="$(mktemp -d /tmp/wvc-kamod-diag-XXXXXX)"
ZIP_PATH="$WORKDIR/artifact.zip"
EXTRACT_DIR="$WORKDIR/extracted"
mkdir -p "$EXTRACT_DIR"
trap 'rm -rf "$WORKDIR"' EXIT

API_URL="https://api.github.com/repos/${REPO}/actions/artifacts/${ARTIFACT_ID}/zip"
META_URL="https://api.github.com/repos/${REPO}/actions/artifacts/${ARTIFACT_ID}"

print_header() {
    printf '\n===== %s =====\n' "$1"
}

validate_zip() {
    [[ -s "$ZIP_PATH" ]] || return 1
    unzip -tq "$ZIP_PATH" >/dev/null 2>&1
}

fetch_with_token() {
    local token="$1"
    curl \
        --fail \
        --location \
        --silent \
        --show-error \
        --retry 3 \
        --retry-delay 1 \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        -H "Authorization: Bearer ${token}" \
        "$API_URL" \
        -o "$ZIP_PATH"
}

find_github_token() {
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
    if [[ -n "$token" ]]; then
        printf '%s' "$token"
        return 0
    fi

    return 1
}

print_header "SOURCE"
echo "repo:          $REPO"
echo "branch:        $BRANCH"
echo "workflow run:  $ARTIFACT_RUN_ID"
echo "artifact id:   $ARTIFACT_ID"
echo "artifact name: $ARTIFACT_NAME"
echo "source SHA:    $ARTIFACT_HEAD_SHA"
echo "target node:   $NODE_ID"

print_header "ARTIFACT METADATA"
META_JSON="$(
    curl \
        --fail \
        --silent \
        --show-error \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        "$META_URL"
)"

python3 - "$ARTIFACT_ID" "$ARTIFACT_NAME" "$ARTIFACT_HEAD_SHA" <<'PY' <<<"$META_JSON"
import json
import sys

expected_id = int(sys.argv[1])
expected_name = sys.argv[2]
expected_sha = sys.argv[3]
meta = json.load(sys.stdin)

errors = []
if meta.get("id") != expected_id:
    errors.append(f"artifact id {meta.get('id')!r} != {expected_id}")
if meta.get("name") != expected_name:
    errors.append(f"artifact name {meta.get('name')!r} != {expected_name!r}")
if meta.get("expired") is True:
    errors.append("artifact is expired")
run = meta.get("workflow_run") or {}
if run.get("head_sha") != expected_sha:
    errors.append(f"artifact head_sha {run.get('head_sha')!r} != {expected_sha}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PASS: artifact metadata matches expected CI build")
print("expires_at:", meta.get("expires_at"))
print("digest:    ", meta.get("digest"))
PY

print_header "DOWNLOAD"
rm -f "$ZIP_PATH"

# Try anonymous first. If GitHub requires authentication, transparently retry
# using a locally available token without ever printing it.
if curl \
    --fail \
    --location \
    --silent \
    --show-error \
    --retry 2 \
    --retry-delay 1 \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "$API_URL" \
    -o "$ZIP_PATH" 2>/dev/null && validate_zip; then
    echo "PASS: artifact downloaded anonymously"
else
    rm -f "$ZIP_PATH"
    TOKEN="$(find_github_token || true)"

    if [[ -z "$TOKEN" && -t 0 ]]; then
        echo "GitHub requires authentication to download this Actions artifact."
        read -r -s -p "GitHub token (Actions: read; Enter = abort): " TOKEN
        echo
    fi

    if [[ -z "$TOKEN" ]]; then
        echo "FAIL: no GitHub token available for Actions artifact download" >&2
        echo "Set GITHUB_TOKEN or authenticate GitHub CLI with: gh auth login" >&2
        exit 1
    fi

    fetch_with_token "$TOKEN"
    unset TOKEN

    if ! validate_zip; then
        echo "FAIL: downloaded artifact is not a valid ZIP archive" >&2
        exit 1
    fi
    echo "PASS: artifact downloaded with local GitHub credentials"
fi

print_header "EXTRACT + VERIFY"
unzip -q "$ZIP_PATH" "$ZIP_MEMBER" -d "$EXTRACT_DIR"
SOURCE_IMAGE="$EXTRACT_DIR/$ZIP_MEMBER"

ACTUAL_SIZE="$(stat -c '%s' "$SOURCE_IMAGE")"
ACTUAL_SHA256="$(sha256sum "$SOURCE_IMAGE" | awk '{print $1}')"
FIRST_BYTE="$(python3 - "$SOURCE_IMAGE" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_bytes()[:1].hex())
PY
)"

printf 'size:     %s\n' "$ACTUAL_SIZE"
printf 'sha256:   %s\n' "$ACTUAL_SHA256"
printf 'ESP magic: 0x%s\n' "$FIRST_BYTE"

[[ "$ACTUAL_SIZE" == "$EXPECTED_SIZE" ]] || {
    echo "FAIL: image size mismatch; expected $EXPECTED_SIZE" >&2
    exit 1
}
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || {
    echo "FAIL: image SHA-256 mismatch; expected $EXPECTED_SHA256" >&2
    exit 1
}
[[ "$FIRST_BYTE" == "e9" ]] || {
    echo "FAIL: image does not start with ESP app magic 0xE9" >&2
    exit 1
}
echo "PASS: exact diagnostic application image verified"

print_header "COPY IMAGE"
install -m 0644 "$SOURCE_IMAGE" "$TARGET_IMAGE"
COPIED_SHA256="$(sha256sum "$TARGET_IMAGE" | awk '{print $1}')"
[[ "$COPIED_SHA256" == "$EXPECTED_SHA256" ]] || {
    echo "FAIL: copied image SHA-256 mismatch" >&2
    exit 1
}
echo "PASS: copied to $TARGET_IMAGE"

print_header "SERVICE-PLANE PRECHECK"
[[ "$(systemctl is-active wvc-service-agent.service)" == "active" ]] || {
    echo "FAIL: wvc-service-agent.service is not active" >&2
    exit 1
}
[[ "$(systemctl is-enabled wvc-service-agent.service)" == "enabled" ]] || {
    echo "FAIL: wvc-service-agent.service is not enabled" >&2
    exit 1
}
echo "PASS: service agent enabled + active"

STATUS_JSON="$(sudo -u wentylacja wvc-servicectl status)"
python3 - "$NODE_ID" <<'PY' <<<"$STATUS_JSON"
import json
import sys

node_id = sys.argv[1]
data = json.load(sys.stdin)
if data.get("ok") is not True:
    raise SystemExit("FAIL: service status returned ok != true")
agent = data.get("agent") or {}
network = data.get("network") or {}
if agent.get("ready") is not True:
    raise SystemExit("FAIL: service agent ready != true")
if network.get("ready") is not True:
    raise SystemExit("FAIL: service network ready != true")

nodes = {n.get("node_id"): n for n in data.get("nodes", [])}
node = nodes.get(node_id)
if not node:
    raise SystemExit(f"FAIL: {node_id} is not registered")

print("target online:  ", node.get("online"))
print("target address: ", node.get("source_ip"))
print("target firmware:", node.get("firmware"))
print("target sensor:  ", node.get("sensor_state"))
print("target RS-485:  ", node.get("rs485_ready"))
print("target Modbus:  ", node.get("modbus_monitor_ready"))

node1 = nodes.get("sensor-node-1")
if node1:
    print("control node-1 firmware:", node1.get("firmware"))
PY

print_header "CURRENT OTA STATUS"
sudo -u wentylacja wvc-servicectl ota-status "$NODE_ID"

if [[ $APPLY -eq 0 ]]; then
    print_header "READY"
    echo "Precheck PASS. Image is ready at: $TARGET_IMAGE"
    echo "No OTA was started. Re-run with --apply to update ONLY $NODE_ID."
    exit 0
fi

print_header "OTA INSTALL: $NODE_ID ONLY"
echo "image:  $TARGET_IMAGE"
echo "sha256: $EXPECTED_SHA256"
echo "expected firmware after reboot: $EXPECTED_FIRMWARE"

echo
sudo -u wentylacja wvc-servicectl \
    ota-install \
    "$NODE_ID" \
    "$TARGET_IMAGE" \
    --wait-timeout 300

print_header "POSTCHECK"
FINAL_JSON="$(sudo -u wentylacja wvc-servicectl status)"
python3 - "$NODE_ID" "$EXPECTED_FIRMWARE" <<'PY' <<<"$FINAL_JSON"
import json
import sys

node_id = sys.argv[1]
expected = sys.argv[2]
data = json.load(sys.stdin)
nodes = {n.get("node_id"): n for n in data.get("nodes", [])}
node = nodes.get(node_id)
if not node:
    raise SystemExit(f"FAIL: {node_id} missing after OTA")

print("node-2 online:   ", node.get("online"))
print("node-2 firmware: ", node.get("firmware"))
print("node-2 partition:", node.get("ota_partition"))
print("node-2 pending:  ", node.get("ota_pending"))
print("node-2 RS-485:   ", node.get("rs485_ready"))
print("node-2 Modbus:   ", node.get("modbus_monitor_ready"))

node1 = nodes.get("sensor-node-1")
if node1:
    print("node-1 firmware: ", node1.get("firmware"))

if node.get("firmware") != expected:
    raise SystemExit(
        f"FAIL: node-2 firmware {node.get('firmware')!r} != expected {expected!r}"
    )
if node.get("ota_pending") is not False:
    raise SystemExit("FAIL: node-2 OTA image is still pending")

print("PASS: diagnostic firmware active and confirmed on sensor-node-2")
PY

print_header "DONE"
echo "KAmod transport diagnostic OTA: PASS"
echo "sensor-node-2 -> $EXPECTED_FIRMWARE"
echo "sensor-node-1 was not targeted by this script"
