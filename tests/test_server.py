import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ventilation_core.runtime.server import CoreServer


class FakeService:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class CoreServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_service_is_closed_when_socket_startup_fails(self) -> None:
        service = FakeService()
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "ventilation-core.sock"
            server = CoreServer(
                service=service,  # type: ignore[arg-type]
                socket_path=socket_path,
                health_interval_seconds=1.0,
            )

            with patch(
                "ventilation_core.runtime.server.asyncio.start_unix_server",
                new=AsyncMock(side_effect=OSError("socket startup failed")),
            ):
                with self.assertRaisesRegex(OSError, "socket startup failed"):
                    await server.run()

            self.assertEqual(service.close_calls, 1)
            self.assertFalse(socket_path.exists())


if __name__ == "__main__":
    unittest.main()
