from __future__ import annotations

import unittest

from ventilation_core.telemetry.http_client import AIBridgeTelemetryClient
from ventilation_core.telemetry.main import build_batch_sender


class TelemetryMainTest(unittest.TestCase):
    def test_missing_sink_selects_capture_only_mode(self) -> None:
        self.assertIsNone(build_batch_sender(None, 5.0))
        self.assertIsNone(build_batch_sender("", 5.0))

    def test_configured_sink_builds_http_client(self) -> None:
        sender = build_batch_sender("http://127.0.0.1:8080", 7.5)
        self.assertIsInstance(sender, AIBridgeTelemetryClient)


if __name__ == "__main__":
    unittest.main()
