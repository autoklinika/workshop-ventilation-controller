import asyncio
import json
import unittest
from pathlib import Path

from ventilation_core.runtime.server import CoreServer


class DisconnectingWriter:
    def __init__(self) -> None:
        self.payload = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.payload += data

    async def drain(self) -> None:
        raise ConnectionResetError("client closed")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        raise ConnectionResetError("client already closed")


class RuntimeDisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnected_client_does_not_escape_handler(self) -> None:
        server = CoreServer(
            service=object(),  # unsupported command does not touch service
            socket_path=Path("/tmp/unused-ventilation-core.sock"),
            health_interval_seconds=1.0,
        )
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"command":"unsupported"}\n')
        reader.feed_eof()
        writer = DisconnectingWriter()

        await server._handle_client(reader, writer)

        self.assertTrue(writer.closed)
        response = json.loads(writer.payload.decode("utf-8"))
        self.assertFalse(response["ok"])
        self.assertIn("Unsupported command", response["error"])


if __name__ == "__main__":
    unittest.main()
