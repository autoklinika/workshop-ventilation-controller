import unittest
from pathlib import Path

from ventilation_core.ctl import build_parser, build_request
from ventilation_core.domain.aero_control import (
    AeroControlCommand,
    AeroControlExecutionState,
    AeroControlResult,
)
from ventilation_core.runtime.server import CoreServer


class FakeService:
    def __init__(self) -> None:
        self.commands: list[AeroControlCommand] = []

    def control_aero(self, command: AeroControlCommand) -> AeroControlResult:
        self.commands.append(command)
        return AeroControlResult(
            command=command,
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=0,
            readback_value=command.value,
            recovered=True,
            physical_confirmation=True,
        )


class AeroControlCliTests(unittest.TestCase):
    def test_builds_speed_request(self) -> None:
        args = build_parser().parse_args(["aero-speed", "2"])
        self.assertEqual(build_request(args), {"command": "aero-speed", "speed": 2})

    def test_builds_airing_request(self) -> None:
        args = build_parser().parse_args(["aero-airing", "on"])
        self.assertEqual(
            build_request(args),
            {"command": "aero-airing", "enabled": True},
        )

    def test_cli_rejects_speed_outside_contract(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["aero-speed", "4"])


class AeroControlApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = FakeService()
        self.server = CoreServer(
            self.service,  # type: ignore[arg-type]
            Path("/tmp/not-used.sock"),
            health_interval_seconds=1.0,
        )

    async def test_dispatches_speed_through_control_boundary(self) -> None:
        response = await self.server._dispatch({"command": "aero-speed", "speed": 3})
        self.assertTrue(response["ok"])
        self.assertEqual(self.service.commands, [AeroControlCommand.set_speed(3)])
        self.assertEqual(response["aero_control"]["target_value"], 3)

    async def test_dispatches_airing_through_control_boundary(self) -> None:
        response = await self.server._dispatch(
            {"command": "aero-airing", "enabled": True}
        )
        self.assertTrue(response["ok"])
        self.assertEqual(self.service.commands, [AeroControlCommand.set_airing(True)])

    async def test_rejects_non_integer_speed_before_service(self) -> None:
        with self.assertRaisesRegex(ValueError, "integer 0..3"):
            await self.server._dispatch({"command": "aero-speed", "speed": "2"})
        self.assertEqual(self.service.commands, [])

    async def test_rejects_non_boolean_airing_before_service(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            await self.server._dispatch({"command": "aero-airing", "enabled": "on"})
        self.assertEqual(self.service.commands, [])


if __name__ == "__main__":
    unittest.main()
