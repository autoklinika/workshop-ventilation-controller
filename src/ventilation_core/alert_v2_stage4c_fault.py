from __future__ import annotations

import ipaddress
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NFT_FAMILY = "inet"
NFT_TABLE = "wvc_sensor_service"
NFT_CHAIN = "input"
HEARTBEAT_PORT = 45551
SERVICE_ADDRESS = "10.55.0.1"
SERVICE_INTERFACE = "wlan0"
_COMMENT_PREFIX = "wvc-alert-v2-stage4c-heartbeat-drop"
_HANDLE_RE = re.compile(r"\bhandle\s+(\d+)\b")


class Stage4CFaultError(RuntimeError):
    pass


def _run(command: list[str], *, timeout_seconds: float = 3.0) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stage4CFaultError(f"command failed to execute: {' '.join(command)}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise Stage4CFaultError(f"command failed: {' '.join(command)}: {detail}")
    return completed


def validate_service_source_ip(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise Stage4CFaultError(f"invalid service node source IP: {value!r}") from exc
    if parsed.version != 4 or parsed not in ipaddress.ip_network("10.55.0.0/24"):
        raise Stage4CFaultError(
            f"refusing heartbeat fault outside WVC-SERVICE subnet: {value!r}"
        )
    if str(parsed) == SERVICE_ADDRESS:
        raise Stage4CFaultError("refusing to target CM5 service address")
    return str(parsed)


def build_drop_rule_command(source_ip: str, comment: str) -> list[str]:
    source_ip = validate_service_source_ip(source_ip)
    if not comment.startswith(_COMMENT_PREFIX):
        raise Stage4CFaultError("invalid Stage 4C nft comment")
    return [
        "nft",
        "insert",
        "rule",
        NFT_FAMILY,
        NFT_TABLE,
        NFT_CHAIN,
        "iifname",
        SERVICE_INTERFACE,
        "ip",
        "saddr",
        source_ip,
        "ip",
        "daddr",
        SERVICE_ADDRESS,
        "udp",
        "dport",
        str(HEARTBEAT_PORT),
        "counter",
        "drop",
        "comment",
        comment,
    ]


def build_delete_rule_command(handle: int) -> list[str]:
    if isinstance(handle, bool) or not isinstance(handle, int) or handle < 1:
        raise Stage4CFaultError("invalid nft rule handle")
    return [
        "nft",
        "delete",
        "rule",
        NFT_FAMILY,
        NFT_TABLE,
        NFT_CHAIN,
        "handle",
        str(handle),
    ]


def list_input_chain() -> str:
    return _run(
        ["nft", "-a", "list", "chain", NFT_FAMILY, NFT_TABLE, NFT_CHAIN]
    ).stdout


def find_comment_handles(chain_text: str, comment: str) -> list[int]:
    handles: list[int] = []
    for line in chain_text.splitlines():
        if comment not in line:
            continue
        match = _HANDLE_RE.search(line)
        if match is not None:
            handles.append(int(match.group(1)))
    return handles


def find_stage4c_handles(chain_text: str) -> list[int]:
    handles: list[int] = []
    for line in chain_text.splitlines():
        if _COMMENT_PREFIX not in line:
            continue
        match = _HANDLE_RE.search(line)
        if match is not None:
            handles.append(int(match.group(1)))
    return handles


@dataclass
class HeartbeatDropRule:
    source_ip: str
    comment: str
    handle: int | None = None

    @classmethod
    def create(cls, source_ip: str) -> "HeartbeatDropRule":
        source_ip = validate_service_source_ip(source_ip)
        token = f"{os.getpid()}-{int(time.time())}"
        return cls(source_ip=source_ip, comment=f"{_COMMENT_PREFIX}-{token}")

    def install(self) -> int:
        if self.handle is not None:
            raise Stage4CFaultError("Stage 4C heartbeat drop rule is already installed")
        existing = find_stage4c_handles(list_input_chain())
        if existing:
            raise Stage4CFaultError(
                "refusing to start: stale Stage 4C nft rule already exists; "
                f"handles={existing}"
            )
        _run(build_drop_rule_command(self.source_ip, self.comment))
        handles = find_comment_handles(list_input_chain(), self.comment)
        if len(handles) != 1:
            raise Stage4CFaultError(
                f"unable to identify unique Stage 4C nft rule handle: {handles}"
            )
        self.handle = handles[0]
        return self.handle

    def verify_installed(self) -> None:
        if self.handle is None:
            raise Stage4CFaultError("Stage 4C heartbeat drop rule is not installed")
        handles = find_comment_handles(list_input_chain(), self.comment)
        if handles != [self.handle]:
            raise Stage4CFaultError(
                f"Stage 4C heartbeat drop rule changed unexpectedly: {handles}"
            )

    def remove(self) -> None:
        if self.handle is None:
            return
        handle = self.handle
        try:
            _run(build_delete_rule_command(handle))
        finally:
            self.handle = None
        remaining = find_comment_handles(list_input_chain(), self.comment)
        if remaining:
            raise Stage4CFaultError(
                f"Stage 4C heartbeat drop rule still present after cleanup: {remaining}"
            )

    def __enter__(self) -> "HeartbeatDropRule":
        self.install()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        cleanup_error: BaseException | None = None
        try:
            self.remove()
        except BaseException as cleanup_exc:
            cleanup_error = cleanup_exc
        if cleanup_error is not None:
            if exc is None:
                raise cleanup_error
            raise Stage4CFaultError(
                f"fault injection failed and cleanup also failed: {cleanup_error}"
            ) from exc
        return False
