from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
from typing import Any

from ventilation_core.infrastructure.rtc_wake import RtcWakeArmError, RtcWakeArmResult


DEFAULT_RTC_AGENT_SOCKET = Path("/run/wvc-rtc/rtc-wake.sock")
MAX_RESPONSE_BYTES = 4096


class RtcWakeAgentClient:
    """Unprivileged narrow client for the privileged RTC wakealarm agent."""

    def __init__(
        self,
        socket_path: Path = DEFAULT_RTC_AGENT_SOCKET,
        *,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._timeout_seconds = float(timeout_seconds)

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def read_epoch(self) -> int | None:
        response = self._request({"command": "read"})
        value = response.get("wake_epoch")
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RtcWakeArmError("RTC agent returned invalid wake_epoch")
        return value

    def clear(self) -> None:
        response = self._request({"command": "clear"})
        if response.get("wake_epoch") is not None:
            raise RtcWakeArmError("RTC agent did not confirm cleared wakealarm")

    def arm(self, wake_at: datetime, *, minimum_lead_seconds: int = 60) -> RtcWakeArmResult:
        if wake_at.tzinfo is None or wake_at.utcoffset() is None:
            raise ValueError("RTC wake target must be timezone-aware")
        if isinstance(minimum_lead_seconds, bool) or not isinstance(minimum_lead_seconds, int):
            raise ValueError("minimum_lead_seconds must be an integer")
        if minimum_lead_seconds < 1:
            raise ValueError("minimum_lead_seconds must be positive")
        target = wake_at.astimezone(timezone.utc)
        response = self._request(
            {
                "command": "arm",
                "wake_epoch": int(target.timestamp()),
                "minimum_lead_seconds": minimum_lead_seconds,
            }
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RtcWakeArmError("RTC agent arm response has no result")
        requested = result.get("requested_epoch")
        verified_epoch = result.get("verified_epoch")
        requested_at = result.get("requested_at_utc")
        verified = result.get("verified")
        if (
            isinstance(requested, bool)
            or not isinstance(requested, int)
            or isinstance(verified_epoch, bool)
            or not isinstance(verified_epoch, int)
            or not isinstance(requested_at, str)
            or verified is not True
        ):
            raise RtcWakeArmError("RTC agent returned invalid arm verification")
        return RtcWakeArmResult(
            requested_epoch=requested,
            verified_epoch=verified_epoch,
            requested_at_utc=requested_at,
            verified=True,
        )

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout_seconds)
                client.connect(str(self._socket_path))
                client.sendall(encoded)
                raw = self._read_line(client)
        except (OSError, TimeoutError) as exc:
            raise RtcWakeArmError(f"RTC agent unavailable: {exc}") from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RtcWakeArmError("RTC agent returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RtcWakeArmError("RTC agent returned non-object response")
        if decoded.get("ok") is not True:
            raise RtcWakeArmError(str(decoded.get("error") or "RTC agent rejected request"))
        return decoded

    @staticmethod
    def _read_line(client: socket.socket) -> bytes:
        data = bytearray()
        while len(data) < MAX_RESPONSE_BYTES:
            chunk = client.recv(min(512, MAX_RESPONSE_BYTES - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
        if not data:
            raise RtcWakeArmError("RTC agent returned empty response")
        if len(data) >= MAX_RESPONSE_BYTES and b"\n" not in data:
            raise RtcWakeArmError("RTC agent response too large")
        return bytes(data).split(b"\n", 1)[0]
