from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from ventilation_core.application.operator_control import apply_operator_intent
from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.models import CoreState
from ventilation_core.domain.operator_control import OperatorControlIntent
from ventilation_core.domain.shadow import ShadowAutomationState, ShadowZoneProposal


class ControlEngineConfigStore(Protocol):
    def load(self) -> tuple[ControlEngineConfig, int]: ...
    def replace(self, config: ControlEngineConfig) -> int: ...
    def close(self) -> None: ...


class PersistentControlEngineEvaluator:
    """Hot-reloadable persistent SHADOW evaluator with volatile operator intent.

    Configuration is persisted in SQLite.  Operator AUTO/MANUAL intent is
    deliberately process-local and starts from AUTO after every core restart so a
    stale manual override cannot revive silently.  Neither path has actuator
    authority.
    """

    def __init__(
        self,
        store: ControlEngineConfigStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._lock = RLock()
        config, revision = store.load()
        self._config = config
        self._revision = revision
        self._evaluator = self._build(config)
        self._operator_intent = OperatorControlIntent()
        self._operator_revision = 0
        self._closed = False

    def _build(self, config: ControlEngineConfig) -> PolicyShadowAutomationEvaluator:
        return PolicyShadowAutomationEvaluator(config.policy, clock=self._clock)

    @property
    def policy(self):
        with self._lock:
            return self._config.policy

    def evaluate(self, state: CoreState) -> ShadowAutomationState:
        with self._lock:
            evaluator = self._evaluator
            config = self._config
            revision = self._revision
            operator_intent = self._operator_intent
            operator_revision = self._operator_revision
        result = evaluator.evaluate(state)
        result = apply_operator_intent(
            result,
            config.policy,
            operator_intent,
            revision=operator_revision,
        )
        zones = tuple(_attach_sensor_provenance(zone, state) for zone in result.zones)
        return replace(
            result,
            zones=zones,
            configuration_revision=revision,
            configuration_persistent=True,
        )

    def configuration(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._revision,
                "config": self._config.to_dict(),
                "actuation_supported": False,
            }

    def replace_configuration(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        # Parse and fully validate before starting any SQLite write transaction.
        config = ControlEngineConfig.from_dict(payload)
        with self._lock:
            if self._closed:
                raise RuntimeError("Control Engine configuration runtime is closed")
            revision = self._store.replace(config)
            evaluator = self._build(config)
            self._config = config
            self._revision = revision
            self._evaluator = evaluator
            return {
                "revision": revision,
                "config": config.to_dict(),
                "actuation_supported": False,
                "dynamics_reset": True,
            }

    def operator_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._operator_revision,
                "intent": self._operator_intent.to_dict(),
                "persistent": False,
                "reset_on_core_restart": True,
                "actuation_supported": False,
            }

    def replace_operator_intent(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        intent = OperatorControlIntent.from_dict(payload)
        with self._lock:
            if self._closed:
                raise RuntimeError("Control Engine configuration runtime is closed")
            self._operator_intent = intent
            self._operator_revision += 1
            return {
                "revision": self._operator_revision,
                "intent": intent.to_dict(),
                "persistent": False,
                "reset_on_core_restart": True,
                "actuation_supported": False,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._store.close()


def _attach_sensor_provenance(
    zone: ShadowZoneProposal,
    state: CoreState,
) -> ShadowZoneProposal:
    if state.sensor_bus is None or zone.sensor_address is None:
        return zone

    node = next(
        (
            item
            for item in state.sensor_bus.nodes
            if item.slave_address == zone.sensor_address
        ),
        None,
    )
    if node is None:
        return zone

    reading = node.reading
    return replace(
        zone,
        sensor_online=node.online,
        sensor_measurement_valid=node.measurement_valid,
        sensor_measurement_stale=node.measurement_stale,
        sensor_age_seconds=node.age_seconds,
        sensor_last_success_at=node.last_success_at,
        sensor_pm2_5_ug_m3=reading.pm2_5_ug_m3,
        sensor_pm10_0_ug_m3=reading.pm10_0_ug_m3,
        sensor_voc_index=reading.voc_index,
        sensor_nox_index=reading.nox_index,
        sensor_temperature_celsius=reading.temperature_celsius,
    )
