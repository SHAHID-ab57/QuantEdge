"""Tests for the WebSocket connection manager.

A scripted in-process server (see :mod:`tests.websocket.server`) simulates the
remote end: reconnects, heartbeats, pings, and shutdown are all exercised
against it without real network access.
"""

import asyncio

import pytest

from app.ws.config import WebSocketSettings
from app.ws.connection import ConnectionManager, backoff_delay
from app.ws.exceptions import WebSocketError
from tests.websocket.server import MockWSServer, wait_until

HEARTBEAT = '{"type": "heartbeat"}'


def settings(
    url: str,
    *,
    reconnect_delay: float = 0.05,
    max_retries: int = 5,
    heartbeat_timeout: float = 5.0,
    ping_interval: float = 5.0,
    pong_timeout: float = 1.0,
) -> WebSocketSettings:
    """Build fast, test-friendly connection settings."""
    return WebSocketSettings(
        url=url,
        reconnect_delay=reconnect_delay,
        max_retries=max_retries,
        heartbeat_timeout=heartbeat_timeout,
        ping_interval=ping_interval,
        pong_timeout=pong_timeout,
    )


def test_backoff_delay_growth_and_cap() -> None:
    assert backoff_delay(1, 2.0, 60.0) == 2.0
    assert backoff_delay(2, 2.0, 60.0) == 4.0
    assert backoff_delay(3, 2.0, 60.0) == 8.0
    assert backoff_delay(6, 2.0, 60.0) == 60.0
    assert backoff_delay(10, 2.0, 60.0) == 60.0


@pytest.mark.asyncio
async def test_connect_receive_and_shutdown() -> None:
    server = MockWSServer(script=[("send", HEARTBEAT), ("send", '{"type":"ticker","sy":"BTCUSD"}')])
    async with server:
        messages: list[str] = []

        async def on_message(raw: str) -> None:
            messages.append(raw)

        manager = ConnectionManager(settings(server.url), on_message=on_message)
        manager.start()
        await wait_until(lambda: len(messages) == 2)
        assert manager.is_connected

        await manager.close()
        assert not manager.is_connected


@pytest.mark.asyncio
async def test_on_connected_hook_runs_per_connection() -> None:
    server = MockWSServer(script=[("wait", 0.1)])
    async with server:
        connected_count = 0

        async def on_connected() -> None:
            nonlocal connected_count
            connected_count += 1

        manager = ConnectionManager(settings(server.url), on_connected=on_connected)
        manager.start()
        await wait_until(lambda: connected_count == 1)
        await manager.close()


@pytest.mark.asyncio
async def test_reconnect_after_server_close() -> None:
    server = MockWSServer(
        script=[
            ("send", HEARTBEAT),
            ("send", HEARTBEAT),
            ("close", 1011),
        ]
    )
    async with server:
        messages: list[str] = []

        async def on_message(raw: str) -> None:
            messages.append(raw)

        manager = ConnectionManager(settings(server.url), on_message=on_message)
        manager.start()
        await wait_until(lambda: server.connections >= 2)
        await wait_until(lambda: len(messages) >= 3)
        await manager.close()


@pytest.mark.asyncio
async def test_heartbeat_timeout_triggers_reconnect() -> None:
    server = MockWSServer(script=[("send", HEARTBEAT), ("send", HEARTBEAT)])
    async with server:
        manager = ConnectionManager(settings(server.url, heartbeat_timeout=0.1), on_message=None)
        manager.start()
        await wait_until(lambda: server.connections >= 2)
        await manager.close()


@pytest.mark.asyncio
async def test_ping_loop_and_pong_prevents_disconnect() -> None:
    server = MockWSServer(script=[("wait", 0.3)], pong_reply=True)
    async with server:
        ping_count = 0

        async def on_message(raw: str) -> None:
            if raw == '{"type":"pong"}':
                manager.notify_pong()

        async def on_ping() -> None:
            nonlocal ping_count
            ping_count += 1
            await manager.send_json({"type": "ping"})

        manager = ConnectionManager(
            settings(server.url, ping_interval=0.05, pong_timeout=0.5),
            on_message=on_message,
            on_ping=on_ping,
        )
        manager.start()
        await wait_until(lambda: ping_count >= 3)
        await asyncio.sleep(0.2)
        assert server.connections == 1
        assert manager.is_connected
        await manager.close()


@pytest.mark.asyncio
async def test_pong_timeout_triggers_reconnect() -> None:
    server = MockWSServer(script=[("wait", 0.1), ("wait", 0.1)])
    async with server:

        async def on_ping() -> None:
            await manager.send_json({"type": "ping"})

        manager = ConnectionManager(
            settings(server.url, ping_interval=0.05, pong_timeout=0.05),
            on_ping=on_ping,
        )
        manager.start()
        await wait_until(lambda: server.connections >= 2)
        await manager.close()


@pytest.mark.asyncio
async def test_max_retries_exhausted_stops_run() -> None:
    server = MockWSServer(script=[("close", 1011)])
    async with server:
        manager = ConnectionManager(settings(server.url, max_retries=1))
        await manager.run()
        assert server.connections == 1


@pytest.mark.asyncio
async def test_unlimited_retries_keep_going() -> None:
    server = MockWSServer(script=[("close", 1011)])
    async with server:
        manager = ConnectionManager(settings(server.url, max_retries=0))
        manager.start()
        await wait_until(lambda: server.connections >= 3)
        await manager.close()


@pytest.mark.asyncio
async def test_send_fails_when_not_connected() -> None:
    server = MockWSServer()
    async with server:
        manager = ConnectionManager(settings(server.url))
        with pytest.raises(WebSocketError, match="not connected"):
            await manager.send_text("hello")


@pytest.mark.asyncio
async def test_graceful_close_releases_receive_loop() -> None:
    server = MockWSServer(script=[("wait", 0.5)])
    async with server:
        manager = ConnectionManager(settings(server.url))
        manager.start()
        await wait_until(lambda: server.connections == 1)
        await manager.close()
        assert not manager.is_connected
