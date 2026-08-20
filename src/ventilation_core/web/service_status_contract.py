from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol


class ServiceSnapshotProvider(Protocol):
    def get_snapshot(self) -> dict[str, Any]: ...


_OBJECT_PATHS: tuple[tuple[str, ...], ...] = (
    ("system",),
    ("system", "memory"),
    ("system", "root_storage"),
    ("system", "load_average"),
    ("system", "power"),
    ("core",),
    ("core", "setpoints"),
    ("core", "alert_v2"),
    ("hardware",),
    ("hardware", "sensor_bus"),
    ("hardware", "aero"),
    ("hardware", "tacho"),
    ("hardware", "tacho", "supply"),
    ("hardware", "tacho", "extract"),
    ("hardware", "tacho", "supply", "service_status"),
    ("hardware", "tacho", "extract", "service_status"),
    ("hardware", "zigbee"),
    ("network",),
    ("network", "default_route"),
    ("network", "ai_server"),
    ("network", "mqtt"),
    ("network", "service_plane"),
    ("network", "service_plane", "agent"),
    ("network", "service_plane", "network"),
    ("data",),
    ("data", "telemetry"),
    ("data", "telemetry", "rollups"),
    ("data", "alerts"),
    ("ai",),
)

_LIST_OF_OBJECT_PATHS: tuple[tuple[str, ...], ...] = (
    ("summary",),
    ("services",),
    ("hardware", "sen55_nodes"),
    ("network", "interfaces"),
    ("network", "service_plane", "nodes"),
)


def _parent_for_path(snapshot: dict[str, Any], path: tuple[str, ...]) -> tuple[dict[str, Any], str]:
    current = snapshot
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    return current, path[-1]


def _normalize_object_path(snapshot: dict[str, Any], path: tuple[str, ...]) -> None:
    parent, key = _parent_for_path(snapshot, path)
    if not isinstance(parent.get(key), dict):
        parent[key] = {}


def _normalize_object_list_path(snapshot: dict[str, Any], path: tuple[str, ...]) -> None:
    parent, key = _parent_for_path(snapshot, path)
    value = parent.get(key)
    if not isinstance(value, list):
        parent[key] = []
        return
    parent[key] = [item for item in value if isinstance(item, dict)]


class NullSafeServiceStatusProvider:
    """Read-only schema adapter for the SERVICE browser view.

    Linux diagnostics can legitimately be unavailable for one poll. The underlying
    provider represents several such cases with ``None`` (for example no default
    route, or a temporarily unavailable service-agent network snapshot). JavaScript
    treats ``null`` as an object in ``typeof`` checks, so keeping a stable mapping
    shape at the HTTP contract boundary prevents one missing subsection from taking
    down the entire read-only SERVICE page.

    This adapter does not infer health, substitute numeric values, execute commands,
    or change control state. It only converts nullable object/list containers into
    empty containers while preserving the source values that are present.
    """

    def __init__(self, provider: ServiceSnapshotProvider) -> None:
        self._provider = provider

    def get_snapshot(self) -> dict[str, Any]:
        source = self._provider.get_snapshot()
        if not isinstance(source, dict):
            return {
                "available": False,
                "configured": True,
                "read_only": True,
                "error": "invalid SERVICE diagnostic snapshot",
                "summary": [],
                "services": [],
            }

        snapshot = deepcopy(source)
        for path in _OBJECT_PATHS:
            _normalize_object_path(snapshot, path)
        for path in _LIST_OF_OBJECT_PATHS:
            _normalize_object_list_path(snapshot, path)
        return snapshot
