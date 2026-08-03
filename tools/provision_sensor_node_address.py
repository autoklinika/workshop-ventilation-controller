#!/usr/bin/env python3
"""Provision a persistent Modbus address in the sensor node NVS partition."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

NVS_OFFSET = "0x9000"
NVS_SIZE = "0x6000"
MIN_ADDRESS = 1
MAX_ADDRESS = 247


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Port USB KAmod, np. COM9")
    parser.add_argument("--address", required=True, type=int, help="Adres Modbus 1..247")
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Tylko wygeneruj obraz NVS, bez zapisu do urządzenia",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Opcjonalna ścieżka wyjściowa obrazu NVS",
    )
    return parser.parse_args()


def find_nvs_generator() -> Path:
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        raise SystemExit(
            "Brak IDF_PATH. Uruchom skrypt w terminalu ESP-IDF otwartym z VS Code."
        )

    generator = (
        Path(idf_path)
        / "components"
        / "nvs_flash"
        / "nvs_partition_generator"
        / "nvs_partition_gen.py"
    )
    if not generator.is_file():
        raise SystemExit(f"Nie znaleziono generatora NVS: {generator}")
    return generator


def run(command: list[str]) -> None:
    print("+", subprocess.list2cmdline(command))
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    if not MIN_ADDRESS <= args.address <= MAX_ADDRESS:
        raise SystemExit("Adres Modbus musi należeć do zakresu 1..247")

    generator = find_nvs_generator()

    with tempfile.TemporaryDirectory(prefix="wvc-stage2b-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        csv_path = temp_dir / "sensor_node_nvs.csv"
        generated_bin = temp_dir / "sensor_node_nvs.bin"
        csv_path.write_text(
            "key,type,encoding,value\n"
            "device_config,namespace,,\n"
            f"modbus_addr,data,u8,{args.address}\n",
            encoding="utf-8",
        )

        run(
            [
                sys.executable,
                str(generator),
                "generate",
                str(csv_path),
                str(generated_bin),
                NVS_SIZE,
            ]
        )

        output_path = args.output.resolve() if args.output else None
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(generated_bin.read_bytes())
            print(f"Obraz NVS zapisany: {output_path}")

        if args.generate_only:
            if output_path is None:
                raise SystemExit("Dla --generate-only podaj również --output")
            print(f"Adres {args.address} wygenerowany bez flashowania.")
            return 0

        print(
            "UWAGA: operacja zastępuje zawartość partycji NVS urządzenia. "
            "Nie kasuje firmware ani partycji OTA."
        )
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
                str(generated_bin),
            ]
        )

    print(
        f"Zapisano trwały adres Modbus {args.address}. "
        "Po restarcie sprawdź log 'resolved Modbus slave address'."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Polecenie zakończyło się błędem: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
