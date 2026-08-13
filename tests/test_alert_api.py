import unittest
from dataclasses import replace
from pathlib import Path

from ventilation_core.ctl import build_parser, build_request
from ventilation_core.domain.alerts import AlertRecord
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, AlarmState, CoreState, FanSetpoints, VentilationMode
from ventilation_core.runtime.server import CoreServer


class FakeAlertService:
    def __init__(self) -> None:
        self.acknowledged = []
        self.record = AlertRecord(alert_id=7, key="aero-bus:communication", code=AlarmCode.AERO_BUS_UNAVAILABLE, source="aero_bus", severity=AlarmSeverity.WARNING, message="Rekuperator AERO: brak poprawnej komunikacji", detail="timeout", active_since="2026-08-13T17:00:00+00:00", acknowledged_at=None, cleared_at=None, occurrences=3)

    def state(self) -> CoreState:
        alarm = AlarmState(code=self.record.code, severity=self.record.severity, message=self.record.message, active_since=self.record.active_since, last_error=self.record.detail, occurrences=self.record.occurrences, alert_id=self.record.alert_id, source=self.record.source, acknowledged_at=self.record.acknowledged_at)
        return CoreState(mode=VentilationMode.STOP, setpoints=FanSetpoints.stopped(), hardware_ready=True, active_alarms=(alarm,))

    def active_alerts(self):
        return (self.record,) if self.record.active else ()

    def alert_history(self, limit: int = 200):
        return (self.record,)[:limit]

    def acknowledge_alert(self, alert_id: int) -> AlertRecord:
        self.acknowledged.append(alert_id)
        self.record = replace(self.record, acknowledged_at="2026-08-13T17:01:00+00:00")
        return self.record


class AlertCliTests(unittest.TestCase):
    def test_builds_requests(self) -> None:
        args = build_parser().parse_args(["alerts", "--limit", "50"])
        self.assertEqual(build_request(args), {"command": "alerts", "limit": 50})
        args = build_parser().parse_args(["ack-alert", "7"])
        self.assertEqual(build_request(args), {"command": "ack-alert", "alert_id": 7})


class AlertApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = FakeAlertService()
        self.server = CoreServer(self.service, Path("/tmp/not-used.sock"), health_interval_seconds=1.0)  # type: ignore[arg-type]

    async def test_alerts_returns_core_active_and_history(self) -> None:
        response = await self.server._dispatch({"command": "alerts", "limit": 20})
        self.assertTrue(response["ok"])
        self.assertEqual(response["active"][0]["alert_id"], 7)
        self.assertEqual(response["history"][0]["alert_id"], 7)
        self.assertTrue(response["active"][0]["active"])
        self.assertIsNone(response["active"][0]["cleared_at"])
        self.assertEqual(response["active"][0]["key"], "aero-bus:communication")
        self.assertEqual(set(response["active"][0]), set(response["history"][0]))

    async def test_acknowledge_is_dispatched_to_core_by_id(self) -> None:
        response = await self.server._dispatch({"command": "ack-alert", "alert_id": 7})
        self.assertEqual(self.service.acknowledged, [7])
        self.assertTrue(response["alert"]["acknowledged"])
        self.assertTrue(response["state"]["active_alarms"][0]["acknowledged"])

    async def test_rejects_invalid_contract_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive integer"):
            await self.server._dispatch({"command": "ack-alert", "alert_id": True})
        with self.assertRaisesRegex(ValueError, "range 1..1000"):
            await self.server._dispatch({"command": "alerts", "limit": 1001})


if __name__ == "__main__":
    unittest.main()
