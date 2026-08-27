from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.models import CoreState
from ventilation_core.domain.shadow import ShadowAutomationState


class ControlEngineConfigStore(Protocol):
    def load(self) -> tuple[ControlEngineConfig, int]: ...
    def replace(self, config: ControlEngineConfig) -> int: ...
    def close(self) -> None: ...


class PersistentControlEngineEvaluator:
    """Hot-reloadable persistent SHADOW evaluator with no actuator authority.

    Replacing configuration atomically swaps the whole deterministic evaluator,
    intentionally resetting hysteresis/debounce state so thresholds are never mixed
    across revisions. The wrapped evaluator itself still reports
    ``actuation_supported=False`` and has no DAC/AERO port.
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
            revision = self._revision
        result = evaluator.evaluate(state)
        return replace(
            result,
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

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._store.close()
