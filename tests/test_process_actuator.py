import threading
import unittest

from ventilation_core.infrastructure.process_actuator import (
    HardwareWorkerError,
    ProcessIsolatedActuator,
)


class ProcessIsolatedActuatorTest(unittest.TestCase):
    def test_worker_restart_rejects_non_recovery_command(self) -> None:
        actuator = ProcessIsolatedActuator.__new__(ProcessIsolatedActuator)
        actuator._lock = threading.RLock()
        actuator._ready = True
        actuator._last_error = None
        actuator._ensure_worker = lambda: True

        with self.assertRaises(HardwareWorkerError):
            actuator._request("apply", supply_voltage=2.0, extract_voltage=0.0)

        self.assertFalse(actuator._ready)
        self.assertIn("safe recovery", actuator._last_error)
