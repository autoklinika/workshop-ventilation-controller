from __future__ import annotations

"""Operator PIN gate for the *physical* AUTO resume command.

MANUAL/HOLD never needs a PIN. No PIN or hash is exposed through a status
response. The file is owned by wentylacja with mode 0600 and read afresh so
an operator can rotate the credential without restarting ventilation-core.
"""

import hashlib
import json
import os
import secrets
import stat
import time
from pathlib import Path
from threading import Lock


class AutoModeAuthorizationError(RuntimeError):
    def __init__(self, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.status = status


def hashed_pin_record(pin: str) -> dict[str, str | int]:
    if not isinstance(pin, str) or not pin.isascii() or not pin.isdecimal() or not 6 <= len(pin) <= 12:
        raise ValueError("Operator PIN must contain 6–12 ASCII digits")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode("ascii"), salt=salt, n=2**14, r=8, p=1)
    return {"schema_version": 1, "salt_hex": salt.hex(), "hash_hex": digest.hex()}


class AutoModePinVerifier:
    MAX_ATTEMPTS = 5
    WINDOW_SECONDS = 120.0
    LOCKOUT_SECONDS = 300.0

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = Lock()
        self._attempts: list[float] = []
        self._locked_until = 0.0

    def _read(self) -> tuple[bytes, bytes] | None:
        try:
            info = self.path.stat()
            if info.st_uid != os.geteuid() or info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                return None
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            if doc.get("schema_version") != 1:
                return None
            salt = bytes.fromhex(doc["salt_hex"])
            digest = bytes.fromhex(doc["hash_hex"])
            if len(salt) != 16 or len(digest) != 64:
                return None
            return salt, digest
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    @property
    def configured(self) -> bool:
        return self._read() is not None

    def require(self, pin: object) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._locked_until:
                raise AutoModeAuthorizationError(
                    "Blokada PIN po nieudanych próbach; użyj lokalnego CLI", 429
                )
            self._attempts = [t for t in self._attempts if now - t < self.WINDOW_SECONDS]
            entry = self._read()
            if entry is None:
                raise AutoModeAuthorizationError(
                    "PIN operatora AUTO nie jest skonfigurowany na CM5", 503
                )
            if not isinstance(pin, str) or not pin.isascii() or not pin.isdecimal() or not 6 <= len(pin) <= 12:
                matched = False
            else:
                salt, expected = entry
                actual = hashlib.scrypt(pin.encode("ascii"), salt=salt, n=2**14, r=8, p=1)
                matched = secrets.compare_digest(actual, expected)
            if not matched:
                self._attempts.append(now)
                if len(self._attempts) >= self.MAX_ATTEMPTS:
                    self._locked_until = now + self.LOCKOUT_SECONDS
                    self._attempts.clear()
                    raise AutoModeAuthorizationError("Zbyt wiele błędnych prób PIN", 429)
                raise AutoModeAuthorizationError("Niepoprawny PIN operatora AUTO", 403)
            self._attempts.clear()
            self._locked_until = 0.0
