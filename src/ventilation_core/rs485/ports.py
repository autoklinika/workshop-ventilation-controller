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
    interface_type: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _interface_type(path: str, resolved_path: str) -> str:
    names = (Path(path).name, Path(resolved_path).name)
    if any(name.startswith(("ttyAMA", "ttyS", "serial")) for name in names):
        return "onboard-uart"
    if any(name.startswith(("ttyUSB", "ttyACM")) for name in names):
        return "usb-serial"
    return "serial"


def _path_priority(path: str) -> int:
    if path.startswith("/dev/serial/by-id/"):
        return 0
    if path.startswith("/dev/serial/by-path/"):
        return 1
    if path in {"/dev/serial0", "/dev/serial1"}:
        return 2
    if path.startswith("/dev/ttyAMA"):
        return 3
    if path.startswith("/dev/ttyS"):
        return 4
    if path.startswith(("/dev/ttyUSB", "/dev/ttyACM")):
        return 5
    return 6


def discover_serial_ports(candidates: Iterable[str] | None = None) -> list[SerialPortInfo]:
    """Discover USB serial adapters and Raspberry Pi onboard UART devices.

    Multiple aliases that resolve to the same character device are deduplicated.
    A stable by-id/by-path name is preferred for USB interfaces, while serial0/
    serial1 aliases are preferred over raw ttyAMA/ttyS names for onboard UARTs.
    """

    if candidates is None:
        candidates = [
            *glob("/dev/serial/by-id/*"),
            *glob("/dev/serial/by-path/*"),
            *glob("/dev/serial[0-9]*"),
            *glob("/dev/ttyAMA*"),
            *glob("/dev/ttyS*"),
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

        path_text = str(path)
        stable = path_text.startswith(("/dev/serial/by-id/", "/dev/serial/by-path/"))
        info = SerialPortInfo(
            path=path_text,
            resolved_path=resolved,
            stable_path=stable,
            interface_type=_interface_type(path_text, resolved),
        )
        current = by_resolved_path.get(resolved)
        if current is None or _path_priority(info.path) < _path_priority(current.path):
            by_resolved_path[resolved] = info

    return sorted(
        by_resolved_path.values(),
        key=lambda item: (_path_priority(item.path), item.path),
    )
