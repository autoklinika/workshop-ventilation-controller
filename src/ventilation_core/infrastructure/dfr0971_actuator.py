from __future__ import annotations

from ventilation_core.domain.models import FanSetpoints

from .gp8403 import GP8403, GP8403Config


class DFR0971Actuator:
    """Owns one DFR0971 and maps supply/extract to DAC channels 0/1."""

    def __init__(self, bus: int, address: int) -> None:
        self._dac = GP8403(GP8403Config(bus=bus, address=address, output_range_volts=10.0))
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def start(self) -> None:
        self._dac.probe()
        self._dac.configure_output_range()
        self._dac.zero_all()
        self._ready = True

    def apply(self, setpoints: FanSetpoints) -> None:
        if not self._ready:
            raise RuntimeError("DFR0971 actuator is not ready")
        self._dac.set_both_channels(
            setpoints.supply_voltage,
            setpoints.extract_voltage,
        )

    def stop_all(self) -> None:
        if self._ready:
            self._dac.zero_all()

    def close(self) -> None:
        try:
            self.stop_all()
        finally:
            self._ready = False
            self._dac.close()
