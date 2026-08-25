from __future__ import annotations

import importlib
import logging
import time
from types import ModuleType
from typing import Callable, Protocol


LOGGER = logging.getLogger(__name__)


class PowerDomain(Protocol):
    """Minimal host-power dependency used by HostPowerAgent."""

    def start(self) -> None:
        """Claim the GPIO and switch the 12 V domain ON."""

    def power_off(self) -> None:
        """Command the 12 V domain OFF while retaining GPIO ownership."""

    def close(self) -> None:
        """Fail-safe OFF and release GPIO ownership."""


class PowerDomainError(RuntimeError):
    pass


class Dfr0473PowerDomain:
    """Own the active-high GPIO that drives the DFRobot DFR0473 relay.

    The line is first requested as an OUTPUT with an INACTIVE value, then
    switched ACTIVE. This guarantees a defined OFF state before the relay is
    intentionally energized. The request remains owned for the lifetime of the
    host-power agent. Releasing the line lets the DFR0473 board's hardware
    pull-down return the relay input to OFF.
    """

    def __init__(
        self,
        *,
        chip_path: str = "/dev/gpiochip0",
        line_name: str = "GPIO22",
        stabilization_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        gpiod_module: ModuleType | None = None,
    ) -> None:
        if not chip_path:
            raise ValueError("chip_path must not be empty")
        if not line_name:
            raise ValueError("line_name must not be empty")
        if stabilization_seconds < 0.0:
            raise ValueError("stabilization_seconds must be >= 0")

        self._chip_path = chip_path
        self._line_name = line_name
        self._stabilization_seconds = float(stabilization_seconds)
        self._sleep = sleep
        self._gpiod = gpiod_module
        self._request = None
        self._line_offset: int | None = None
        self._commanded_on = False

    @property
    def commanded_on(self) -> bool:
        return self._commanded_on

    def _load_gpiod(self) -> ModuleType:
        if self._gpiod is None:
            self._gpiod = importlib.import_module("gpiod")
        return self._gpiod

    def start(self) -> None:
        if self._request is not None:
            return

        gpiod = self._load_gpiod()
        try:
            with gpiod.Chip(self._chip_path) as chip:
                line_offset = int(chip.line_offset_from_id(self._line_name))

            settings = gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE,
            )
            request = gpiod.request_lines(
                self._chip_path,
                consumer="wvc-dfr0473-12v",
                config={(line_offset,): settings},
            )
        except Exception as exc:
            raise PowerDomainError(
                f"unable to claim DFR0473 control line {self._line_name}: {exc}"
            ) from exc

        self._request = request
        self._line_offset = line_offset

        try:
            request.set_value(line_offset, gpiod.line.Value.ACTIVE)
            self._commanded_on = True
            LOGGER.warning(
                "12 V power domain commanded ON via DFR0473 line=%s",
                self._line_name,
            )
            if self._stabilization_seconds > 0.0:
                self._sleep(self._stabilization_seconds)
        except Exception as exc:
            self._commanded_on = False
            try:
                request.set_value(line_offset, gpiod.line.Value.INACTIVE)
            except Exception:
                LOGGER.exception("unable to restore DFR0473 OFF after startup failure")
            try:
                request.release()
            finally:
                self._request = None
                self._line_offset = None
            raise PowerDomainError(f"unable to switch 12 V power domain ON: {exc}") from exc

    def power_off(self) -> None:
        if self._request is None or self._line_offset is None:
            raise PowerDomainError("DFR0473 power domain is not started")

        gpiod = self._load_gpiod()
        try:
            self._request.set_value(self._line_offset, gpiod.line.Value.INACTIVE)
        except Exception as exc:
            raise PowerDomainError(f"unable to switch 12 V power domain OFF: {exc}") from exc

        self._commanded_on = False
        LOGGER.warning(
            "12 V power domain commanded OFF via DFR0473 line=%s",
            self._line_name,
        )

    def close(self) -> None:
        request = self._request
        if request is None:
            return

        try:
            self.power_off()
        except Exception:
            # Releasing the GPIO request still removes the active drive and the
            # DFR0473 board's hardware pull-down is expected to keep relay OFF.
            LOGGER.exception(
                "unable to command DFR0473 OFF during close; releasing GPIO request"
            )
        finally:
            try:
                request.release()
            finally:
                self._request = None
                self._line_offset = None
                self._commanded_on = False
