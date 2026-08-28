from __future__ import annotations

import unittest
from pathlib import Path


class ControlEngineMainIntegrationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path("src/ventilation_core/main.py").read_text(encoding="utf-8")

    def test_main_bootstraps_control_engine_from_shared_automation_database(self) -> None:
        self.assertIn(
            "from ventilation_core.application.control_engine_bootstrap import build_control_engine_evaluator",
            self.source,
        )
        self.assertIn(
            "shadow_evaluator = build_control_engine_evaluator(args.automation_db)",
            self.source,
        )
        self.assertIn("shadow_evaluator=shadow_evaluator", self.source)
        self.assertNotIn(
            "shadow_evaluator=PolicyShadowAutomationEvaluator(ShadowPolicyV1())",
            self.source,
        )

    def test_main_uses_control_engine_socket_extension(self) -> None:
        self.assertIn(
            "from ventilation_core.runtime.control_engine_server import ControlEngineCoreServer",
            self.source,
        )
        self.assertIn("server = ControlEngineCoreServer(", self.source)
        self.assertNotIn("server = CoreServer(", self.source)

    def test_main_keeps_scheduled_shutdown_explicit_opt_in(self) -> None:
        self.assertIn('"--enable-scheduled-shutdown"', self.source)
        self.assertIn("action=\"store_true\"", self.source)
        self.assertIn("enabled=args.enable_scheduled_shutdown", self.source)

    def test_startup_failure_closes_persistent_evaluator(self) -> None:
        self.assertIn('close_shadow = getattr(shadow_evaluator, "close", None)', self.source)
        self.assertIn("close_shadow()", self.source)


if __name__ == "__main__":
    unittest.main()
