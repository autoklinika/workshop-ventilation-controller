from __future__ import annotations

import logging
from pathlib import Path

from ventilation_core.application.control_engine_runtime import PersistentControlEngineEvaluator
from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator, ShadowAutomationEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.shadow_policy import ShadowPolicyV1
from ventilation_core.infrastructure.sqlite_control_engine_store import SqliteControlEngineStore


LOGGER = logging.getLogger(__name__)


def build_control_engine_evaluator(automation_db: Path) -> ShadowAutomationEvaluator:
    """Build persistent SHADOW runtime, falling back to empty tuning on DB failure.

    A persistence failure must never stop ventilation-core or grant actuation. The
    fallback deliberately has the production default policy with all tuning unset.
    """

    store: SqliteControlEngineStore | None = None
    try:
        store = SqliteControlEngineStore(
            automation_db,
            initial_config=ControlEngineConfig(),
        )
        runtime = PersistentControlEngineEvaluator(store)
        metadata = runtime.configuration()
        LOGGER.info(
            "Control Engine persistent SHADOW configuration loaded revision=%s actuation_supported=false",
            metadata["revision"],
        )
        return runtime
    except Exception:
        LOGGER.exception(
            "Control Engine configuration unavailable; using safe SHADOW policy with tuning unset"
        )
        if store is not None:
            try:
                store.close()
            except Exception:
                LOGGER.exception("Unable to close failed Control Engine configuration store")
        return PolicyShadowAutomationEvaluator(ShadowPolicyV1())
