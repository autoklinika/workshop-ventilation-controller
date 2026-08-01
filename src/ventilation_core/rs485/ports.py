from __future__ import annotations

from dataclasses import asdict, dataclass
from glob import glob
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SerialPortInfo:
    path: str
    resolved_path: str
    stable_path: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def discover_serial_ports(candidates: Iterable[str] | None = None) -> list[SerialPortInfo]:
    if candidates is None:
        candidates = [
            *glob("/dev/serial/by-id/*"),
            *glob("/dev/ttyUSB*"),
            *glob("/dev/ttyACM*"),
        ]

    by_resolved_path: dict[str, SerialPortInfo] = {}
    for candidate in candidates:
        path = Path(candidate)
        try:
            resolved = str(path.resolve(strict=True))
        except FileNotFoundError:
            continue
        stable = str(path).startswith("/dev/serial/by-id/")
        current = by_resolved_path.get(resolved)
        info = SerialPortInfo(str(path), resolved, stable)
        if current is None or (stable and not current.stable_path):
            by_resolved_path[resolved] = info

    return sorted(
        by_resolved_path.values(),
        key=lambda item: (not item.stable_path, item.path),
    )
