#!/usr/bin/env python3
"""Provision Modbus, open service Wi-Fi, and HMAC credentials into sensor-node NVS."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

NVS_OFFSET = "0x9000"
NVS_SIZE = "0x6000"
NODE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
MAC_RE = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="USB port KAmod, e.g. COM9")
    parser.add_argument("--modbus-address", required=True, type=int)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--key-id")
    parser.add_argument("--mac", help="Optional Wi-Fi MAC pin for CM5 registry")
    parser.add_argument("--ssid", default="WVC-SERVICE")
    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="CM5 key registry to create or update; contains secrets",
    )
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def find_nvs_generator() -> Path:
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        raise SystemExit("IDF_PATH is missing; run from an ESP-IDF terminal")
    path = (
        Path(idf_path)
        / "components"
        / "nvs_flash"
        / "nvs_partition_generator"
        / "nvs_partition_gen.py"
    )
    if not path.is_file():
        raise SystemExit(f"NVS generator was not found: {path}")
    return path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"nodes": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid registry JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), dict):
        raise SystemExit("Registry must contain a 'nodes' object")
    return value


def write_registry(path: Path, registry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    if not 1 <= args.modbus_address <= 247:
        raise SystemExit("Modbus address must be in range 1..247")
    if not NODE_ID_RE.fullmatch(args.node_id):
        raise SystemExit("node_id must match [a-z0-9][a-z0-9-]{0,31}")
    key_id = args.key_id or f"{args.node_id}-v1"
    if not KEY_ID_RE.fullmatch(key_id):
        raise SystemExit("key_id contains unsupported characters")
    if not 1 <= len(args.ssid.encode("utf-8")) <= 32:
        raise SystemExit("SSID must contain 1..32 UTF-8 bytes")

    mac = args.mac.upper() if args.mac else None
    if mac is not None and not MAC_RE.fullmatch(mac):
        raise SystemExit("MAC must use AA:BB:CC:DD:EE:FF format")

    auth_key = secrets.token_bytes(32)
    generator = find_nvs_generator()
    registry = load_registry(args.registry)
    registry["nodes"][args.node_id] = {
        "key_id": key_id,
        "hmac_key_hex": auth_key.hex(),
        **({"mac": mac} if mac else {}),
    }

    with tempfile.TemporaryDirectory(prefix="wvc-service-provision-") as temp_name:
        temp = Path(temp_name)
        csv_path = temp / "sensor_node_service_nvs.csv"
        generated = temp / "sensor_node_service_nvs.bin"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerows(
                [
                    ("key", "type", "encoding", "value"),
                    ("device_config", "namespace", "", ""),
                    ("modbus_addr", "data", "u8", args.modbus_address),
                    ("service_cfg", "namespace", "", ""),
                    ("wifi_ssid", "data", "string", args.ssid),
                    ("node_id", "data", "string", args.node_id),
                    ("key_id", "data", "string", key_id),
                    ("auth_key", "data", "hex2bin", auth_key.hex()),
                ]
            )
        run([sys.executable, str(generator), "generate", str(csv_path), str(generated), NVS_SIZE])

        output = args.output.resolve() if args.output else None
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(generated.read_bytes())
            os.chmod(output, 0o600)
        if args.generate_only:
            if output is None:
                raise SystemExit("--generate-only requires --output")
        else:
            run(
                [
                    sys.executable,
                    "-m",
                    "esptool",
                    "--chip",
                    "esp32",
                    "--port",
                    args.port,
                    "--before",
                    "default_reset",
                    "--after",
                    "hard_reset",
                    "write_flash",
                    NVS_OFFSET,
                    str(generated),
                ]
            )

    write_registry(args.registry, registry)
    print(f"Provisioned node_id={args.node_id}, Modbus slave={args.modbus_address}, key_id={key_id}.")
    print("The service AP is open; heartbeat authentication remains HMAC-SHA256 per node.")
    print("Secrets were written only to the local NVS image and the mode-0600 CM5 registry.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
