from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ventilation_core.service_agent import ServiceAgent, build_parser
from ventilation_core.service_heartbeat import HeartbeatError, NodeKey, load_node_keys
from ventilation_core.service_ota import OtaCoordinator, ServiceOtaError

LOGGER = logging.getLogger("wvc.service_agent")
RUNTIME_LEASES_PATH = Path("/run/wvc-sensor-service/dnsmasq-wvc.leases")


class OtaServiceAgent(ServiceAgent):
    def __init__(
        self,
        *,
        keys: dict[str, NodeKey],
        runtime_dir: Path,
        state_dir: Path,
        bind_address: str,
        port: int,
        socket_path: Path,
        stale_after_seconds: float,
        network_probe_interval_seconds: float = 5.0,
    ) -> None:
        self._ota = OtaCoordinator(
            keys=keys,
            state_dir=state_dir,
            leases_path=RUNTIME_LEASES_PATH,
        )
        super().__init__(
            keys=keys,
            runtime_dir=runtime_dir,
            state_dir=state_dir,
            bind_address=bind_address,
            port=port,
            socket_path=socket_path,
            stale_after_seconds=stale_after_seconds,
            network_probe_interval_seconds=network_probe_interval_seconds,
        )

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if command not in {"ota-install", "ota-status"}:
            return super().handle_request(request)

        node_id = request.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            return {"ok": False, "error": "node_id is required"}
        snapshot = self.snapshot()
        nodes = snapshot["nodes"]

        try:
            if command == "ota-status":
                return {"ok": True, "ota": self._ota.status(node_id=node_id, nodes=nodes)}

            image_path = request.get("image_path")
            if not isinstance(image_path, str) or not image_path:
                return {"ok": False, "error": "image_path is required"}
            operation = self._ota.start_install(
                node_id=node_id,
                image_path=Path(image_path),
                nodes=nodes,
            )
            return {"ok": True, "ota": {"node_id": node_id, "operation": operation}}
        except ServiceOtaError as exc:
            return {"ok": False, "error": str(exc)}


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        agent = OtaServiceAgent(
            keys=load_node_keys(args.keys),
            runtime_dir=args.runtime_dir,
            state_dir=args.state_dir,
            bind_address=args.bind,
            port=args.port,
            socket_path=args.socket,
            stale_after_seconds=args.stale_after,
            network_probe_interval_seconds=args.network_probe_interval,
        )
        agent.run()
    except KeyboardInterrupt:
        return 130
    except (OSError, HeartbeatError, ValueError) as exc:
        LOGGER.error("service agent stopped: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
