#!/usr/bin/env python3
"""Configure/rotate physical AUTO mode PIN locally (never in Git or URL)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile

from ventilation_core.web.auto_mode_auth import hashed_pin_record


def main() -> int:
    parser = argparse.ArgumentParser(description="Set WVC AUTO operator PIN on CM5")
    parser.add_argument(
        "--file", type=Path,
        default=Path("/var/lib/workshop-ventilation/auto-mode-pin.json"),
    )
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Interactive local terminal required; never pass PIN on command line")
    print("WVC: ustaw PIN operatora AUTO (6–12 cyfr). MANUAL i STOP nie wymagają PIN.")
    pin = getpass.getpass("Nowy PIN: ")
    check = getpass.getpass("Powtórz PIN: ")
    if pin != check:
        raise SystemExit("PIN niezgodny; bez zmian")
    doc = hashed_pin_record(pin)
    pin = check = ""
    args.file.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".auto-mode-pin-", dir=str(args.file.parent)
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(doc, writer)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, args.file)
        os.chmod(args.file, 0o600)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    print(f"PIN zapisany bezpiecznie w {args.file}; brak hasła jawnego w pliku")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
