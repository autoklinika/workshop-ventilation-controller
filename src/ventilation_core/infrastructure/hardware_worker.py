from __future__ import annotations

import traceback
from multiprocessing.queues import Queue
from typing import Any

from ventilation_core.domain.models import FanSetpoints

from .dfr0971_actuator import DFR0971Actuator


def _reply(response_queue: Queue, request_id: str, **payload: Any) -> None:
    response_queue.put({"request_id": request_id, **payload})


def hardware_worker_main(
    bus: int,
    address: int,
    command_queue: Queue,
    response_queue: Queue,
) -> None:
    """Dedicated hardware process. It is the only process allowed to access I2C."""
    actuator: DFR0971Actuator | None = None
    try:
        actuator = DFR0971Actuator(bus=bus, address=address)
        actuator.start()
        response_queue.put({"request_id": "__startup__", "ok": True})

        while True:
            request = command_queue.get()
            request_id = str(request["request_id"])
            command = request["command"]
            try:
                if command == "apply":
                    actuator.apply(
                        FanSetpoints(
                            supply_voltage=float(request["supply_voltage"]),
                            extract_voltage=float(request["extract_voltage"]),
                        )
                    )
                    _reply(response_queue, request_id, ok=True)
                elif command == "stop":
                    actuator.stop_all()
                    _reply(response_queue, request_id, ok=True)
                elif command == "ping":
                    _reply(response_queue, request_id, ok=True)
                elif command == "shutdown":
                    actuator.stop_all()
                    _reply(response_queue, request_id, ok=True)
                    break
                else:
                    raise ValueError(f"Unsupported hardware command: {command}")
            except Exception as exc:
                _reply(response_queue, request_id, ok=False, error=str(exc))
    except Exception as exc:
        response_queue.put(
            {
                "request_id": "__startup__",
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if actuator is not None:
            try:
                actuator.close()
            except Exception:
                pass
