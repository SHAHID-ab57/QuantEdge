"""In-process scripted WebSocket server for tests.

Serves on a random localhost port and replays a scripted sequence of
actions per connection, so reconnect behavior can be exercised without
real network access. Client frames are captured concurrently with the
script.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any, cast

import websockets
from websockets.exceptions import ConnectionClosedError

Action = tuple[str, object]

PING_TEXT = json.dumps({"type": "ping"}, separators=(",", ":"))
PONG_TEXT = json.dumps({"type": "pong"}, separators=(",", ":"))
HEARTBEAT_TEXT = json.dumps({"type": "heartbeat"}, separators=(",", ":"))


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    """Poll until a callable returns True or the timeout elapses."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached within timeout")


class MockWSServer:
    """Scripted WebSocket server.

    Each connection replays ``script`` (a list of actions) while client
    frames are drained into ``received``.

    Actions are ``(kind, payload)`` tuples:

    - ``("send", text)``: send a text frame.
    - ``("close", code)``: close with the given code.
    - ``("wait", seconds)``: sleep, letting client-side timers fire.

    The script may also be a callable returning the list per connection.
    With ``pong_reply``, every received ``ping`` message is answered with
    a ``pong``. With ``heartbeat_interval``, a ``heartbeat`` is sent every
    N seconds while the connection is open.
    """

    def __init__(
        self,
        script: list[Action] | None = None,
        *,
        pong_reply: bool = False,
        heartbeat_interval: float | None = None,
    ) -> None:
        self.script = script
        self.pong_reply = pong_reply
        self.heartbeat_interval = heartbeat_interval
        self.connections = 0
        self.received: list[str] = []
        self._server: Any = None

    @property
    def url(self) -> str:
        """The ``ws://`` URL of the running server."""
        return f"ws://127.0.0.1:{self.port}"

    async def start(self) -> None:
        """Bind the server to a random localhost port."""
        self._server = await websockets.serve(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Close the server and wait for its handlers."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def __aenter__(self) -> "MockWSServer":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()

    async def _handle(self, ws: Any) -> None:
        """Serve one connection: play the script while draining the client."""
        self.connections += 1
        script = (
            list(self.script) if callable(self.script) else list(self.script or [])
        )
        drain = asyncio.create_task(self._drain(ws))
        heartbeat = None
        if self.heartbeat_interval is not None:
            heartbeat = asyncio.create_task(self._beat(ws, self.heartbeat_interval))
        try:
            for kind, payload in script:
                if kind == "send":
                    await ws.send(payload)
                elif kind == "close":
                    await ws.close(code=cast(int, payload))
                    break
                elif kind == "wait":
                    await asyncio.sleep(cast(float, payload))
        except ConnectionClosedError:
            pass
        await drain
        if heartbeat is not None:
            heartbeat.cancel()

    async def _beat(self, ws: Any, interval: float) -> None:
        """Send heartbeats periodically until the connection closes."""
        try:
            while True:
                await asyncio.sleep(interval)
                await ws.send(HEARTBEAT_TEXT)
        except (ConnectionClosedError, asyncio.CancelledError):
            pass

    async def _drain(self, ws: Any) -> None:
        """Capture client frames, optionally answering pings."""
        try:
            async for raw in ws:
                self.received.append(raw)
                if self.pong_reply and raw == PING_TEXT:
                    await ws.send(PONG_TEXT)
        except ConnectionClosedError:
            pass
