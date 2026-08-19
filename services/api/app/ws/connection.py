"""Async WebSocket connection management.

Owns a single client connection, its reconnect loop with exponential
backoff, heartbeat and pong supervision, and graceful shutdown. The
machinery is protocol-agnostic; protocol specifics plug in through the
lifecycle hooks:

- ``on_connected``: awaited once after every (re)connect, before the
  receive loop starts (use it to authenticate and resubscribe).
- ``on_message``: awaited for every text frame.
- ``on_ping``: awaited every ``ping_interval`` (use it to send a ping); a
  connection that does not produce a pong within ``pong_timeout`` is
  aborted and reconnected.
- ``notify_heartbeat`` / ``notify_pong``: feed received protocol
  heartbeats and pongs into the supervisors.
"""

import asyncio
import json
import logging
import random
from asyncio import CancelledError
from collections.abc import Callable, Coroutine
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Literal

import websockets
from websockets import ConnectionClosed
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import WebSocketException
from websockets.protocol import State

from app.ws.config import WebSocketSettings
from app.ws.exceptions import WebSocketError

logger = logging.getLogger("app.ws.connection")

MessageHandler = Callable[[str], Coroutine[Any, Any, None]]
LifecycleHook = Callable[[], Coroutine[Any, Any, None]]

_ABNORMAL_CLOSE = 1012

ConnectionState = Literal["stopped", "connecting", "connected", "disconnected"]


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff for a failed attempt (1-based), capped."""
    return min(base * (2 ** max(attempt - 1, 0)), cap)


class ConnectionManager:
    """Async WebSocket connection manager with supervised reconnection.

    Args:
        settings: Connection settings (url, timers, retry policy).
        on_connected: Async hook awaited after every (re)connect.
        on_message: Async hook awaited for every received text frame.
        on_ping: Async hook awaited every ``ping_interval``; pings are
            only sent while connected, and a missing pong within
            ``pong_timeout`` forces a reconnect.
    """

    def __init__(
        self,
        settings: WebSocketSettings,
        *,
        on_connected: LifecycleHook | None = None,
        on_message: MessageHandler | None = None,
        on_ping: LifecycleHook | None = None,
    ) -> None:
        self._settings = settings
        self._on_connected = on_connected
        self._on_message = on_message
        self._on_ping = on_ping

        self._ws: ClientConnection | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._monitor_tasks: set[asyncio.Task[None]] = set()
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._heartbeat_event = asyncio.Event()
        self._pong_event = asyncio.Event()
        self._attempt = 0
        self._state: ConnectionState = "stopped"
        self._connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._last_heartbeat_at: datetime | None = None
        self._messages_received = 0

    @property
    def state(self) -> ConnectionState:
        """Current connection lifecycle state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """True while a connection is up and running."""
        return (
            self._connected_event.is_set()
            and self._ws is not None
            and self._ws.state is not State.CLOSED
        )

    @property
    def connected_at(self) -> datetime | None:
        """When the current connection was established, or ``None``."""
        return self._connected_at

    @property
    def last_message_at(self) -> datetime | None:
        """When the last text frame was received, or ``None``."""
        return self._last_message_at

    @property
    def last_heartbeat_at(self) -> datetime | None:
        """When the last protocol heartbeat was received, or ``None``."""
        return self._last_heartbeat_at

    @property
    def messages_received(self) -> int:
        """Number of text frames received across all connections."""
        return self._messages_received

    @property
    def attempts(self) -> int:
        """Number of connection attempts made so far."""
        return self._attempt

    @property
    def uptime_seconds(self) -> float | None:
        """Seconds since the current connection was established, or ``None``."""
        if self._connected_at is None or not self.is_connected:
            return None
        return max((datetime.now(UTC) - self._connected_at).total_seconds(), 0.0)

    def start(self) -> None:
        """Begin connecting in the background; returns immediately."""
        if self._run_task is not None and not self._run_task.done():
            raise WebSocketError("ConnectionManager is already running")
        self._run_task = asyncio.create_task(self._run(), name="ws-connection-run")

    async def run(self) -> None:
        """Run the connection loop until shutdown or retries exhausted."""
        if self._run_task is None or self._run_task.done():
            self._run_task = asyncio.create_task(self._run(), name="ws-connection-run")
        await self._run_task

    async def close(self) -> None:
        """Gracefully stop: close the socket, stop supervision, stop retries."""
        self._stop_event.set()
        ws = self._ws
        if ws is not None and ws.state is not State.CLOSED:
            with suppress(WebSocketException, OSError):
                await ws.close(code=1000, reason="shutdown")
        await self._stop_monitors()
        task = self._run_task
        if task is not None and not task.done():
            task.cancel()
            with suppress(CancelledError):
                await task

    async def send_text(self, text: str) -> None:
        """Send a text frame; raises :class:`WebSocketError` when not connected."""
        if not self.is_connected:
            raise WebSocketError("cannot send: WebSocket is not connected")
        assert self._ws is not None
        await self._ws.send(text)

    async def send_json(self, payload: dict[str, object]) -> None:
        """Serialize and send a JSON message."""
        await self.send_text(json.dumps(payload, separators=(",", ":")))

    def notify_heartbeat(self) -> None:
        """Reset the heartbeat supervisor (feed from protocol heartbeats)."""
        self._heartbeat_event.set()
        self._last_heartbeat_at = datetime.now(UTC)

    def notify_pong(self) -> None:
        """Record a received pong."""
        self._pong_event.set()

    async def abort(self, reason: str) -> None:
        """Force the current connection down; the run loop will reconnect."""
        logger.warning("WebSocket aborting connection: %s", reason)
        ws = self._ws
        if ws is not None and ws.state is not State.CLOSED:
            with suppress(WebSocketException, OSError):
                await ws.close(code=_ABNORMAL_CLOSE, reason=reason)

    @staticmethod
    def _close_description(exc: ConnectionClosed) -> str:
        """Best-effort human description of a closed connection."""
        close = exc.rcvd if exc.rcvd is not None else exc.sent
        if close is not None and close.reason:
            return f"{close.code} {close.reason}"
        return exc.__class__.__name__

    async def _run(self) -> None:
        """Reconnect loop: connect, supervise, and retry with backoff."""
        while not self._stop_event.is_set():
            if self._settings.max_retries and self._attempt >= self._settings.max_retries:
                logger.error(
                    "WebSocket giving up after %d attempts", self._attempt
                )
                break
            self._attempt += 1
            self._state = "connecting"
            try:
                await self._connect_once()
            except CancelledError:
                raise
            except Exception:
                logger.exception(
                    "WebSocket unexpected failure on attempt %d", self._attempt
                )
            if self._stop_event.is_set():
                break
            delay = backoff_delay(
                self._attempt,
                self._settings.reconnect_delay,
                self._settings.max_backoff,
            )
            jittered = delay * (1.0 + random.random() * 0.1)
            logger.warning(
                "WebSocket reconnecting in %.2fs (attempt %d)", jittered, self._attempt
            )
            try:
                await asyncio.sleep(jittered)
            except CancelledError:
                raise
        self._state = "stopped"
        self._connected_at = None
        logger.info("WebSocket run loop stopped")

    async def _connect_once(self) -> None:
        """Establish one connection and run its receive loop."""
        try:
            self._ws = await websockets.connect(
                self._settings.url,
                open_timeout=self._settings.connect_timeout,
                close_timeout=self._settings.close_timeout,
                ping_interval=None,
                ping_timeout=None,
            )
        except (OSError, WebSocketException) as exc:
            logger.warning(
                "WebSocket connect failed on attempt %d: %s", self._attempt, exc
            )
            return

        ws = self._ws
        self._connected_event.set()
        self._state = "connected"
        self._connected_at = datetime.now(UTC)
        logger.info(
            "WebSocket connected to %s (attempt %d)", self._settings.url, self._attempt
        )
        setup_task: asyncio.Task[None] | None = None
        try:
            if self._on_connected is not None:
                setup_task = asyncio.create_task(
                    self._on_connected(), name="ws-on-connected"
                )
                # Frames buffered before the receive loop starts are processed
                # synchronously; yield once so the setup hook runs first.
                await asyncio.sleep(0)
            self._start_monitors()
            async for raw in ws:
                if self._stop_event.is_set():
                    break
                if isinstance(raw, bytes):
                    logger.warning("WebSocket received a binary frame; ignoring")
                    continue
                self._messages_received += 1
                self._last_message_at = datetime.now(UTC)
                if self._on_message is not None:
                    await self._on_message(raw)
        except ConnectionClosed as exc:
            logger.warning(
                "WebSocket connection closed: %s", self._close_description(exc)
            )
        except CancelledError:
            raise
        except Exception:
            logger.exception("WebSocket receive loop crashed")
        finally:
            await self._stop_monitors()
            if setup_task is not None:
                if setup_task.done():
                    with suppress(CancelledError):
                        setup_task.exception()
                else:
                    setup_task.cancel()
            self._connected_event.clear()
            self._state = "disconnected"
            self._connected_at = None
            with suppress(WebSocketException, OSError):
                await ws.close()
            self._ws = None
            logger.info("WebSocket disconnected from %s", self._settings.url)

    def _start_monitors(self) -> None:
        """Start heartbeat and (when configured) ping supervision tasks."""
        self._heartbeat_event.clear()
        self._pong_event.clear()
        self._monitor_tasks.add(
            asyncio.create_task(self._heartbeat_monitor(), name="ws-heartbeat")
        )
        if self._on_ping is not None:
            self._monitor_tasks.add(
                asyncio.create_task(self._ping_loop(), name="ws-ping")
            )

    async def _stop_monitors(self) -> None:
        """Cancel and drain all supervision tasks."""
        tasks = list(self._monitor_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._monitor_tasks.clear()

    async def _heartbeat_monitor(self) -> None:
        """Abort the connection when no heartbeat arrives in time."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._heartbeat_event.wait(),
                    timeout=self._settings.heartbeat_timeout,
                )
            except TimeoutError:
                logger.warning(
                    "WebSocket heartbeat timeout after %.1fs",
                    self._settings.heartbeat_timeout,
                )
                await self.abort("heartbeat timeout")
                return
            except CancelledError:
                return
            self._heartbeat_event.clear()

    async def _ping_loop(self) -> None:
        """Ping periodically and abort the connection when no pong arrives."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._settings.ping_interval)
            except CancelledError:
                return
            if not self.is_connected or self._stop_event.is_set():
                return
            if self._on_ping is not None:
                await self._on_ping()
            self._pong_event.clear()
            try:
                await asyncio.wait_for(
                    self._pong_event.wait(), timeout=self._settings.pong_timeout
                )
            except TimeoutError:
                logger.warning(
                    "WebSocket pong timeout after %.1fs", self._settings.pong_timeout
                )
                await self.abort("pong timeout")
                return
            except CancelledError:
                return
