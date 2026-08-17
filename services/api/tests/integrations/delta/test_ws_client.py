"""End-to-end tests for the Delta WebSocket client against a scripted server.

Verifies the full protocol wiring: key-auth signing, heartbeat/ping/pong
feeding, subscription payloads, resubscribe-on-reconnect, event dispatch,
and credential validation.
"""

import asyncio
import json
from typing import Any, cast

import pytest

from app.integrations.delta import AuthenticationError
from app.integrations.delta.websocket import models as events
from app.integrations.delta.websocket.auth import sign_key_auth
from app.integrations.delta.websocket.client import DeltaWebSocketClient
from app.ws.config import WebSocketSettings
from app.ws.models import UnknownWSEvent, WSEvent
from tests.ws.server import MockWSServer, wait_until

API_KEY = "test-key"
API_SECRET = "test-secret"

AUTH_OK = (
    '{"type":"key-auth","success":true,"status_code":200,'
    '"status":"authenticated"}'
)
AUTH_FAIL = (
    '{"type":"key-auth","success":false,"status_code":401,'
    '"status":"invalid_signature","message":"Invalid Signature"}'
)
ACK = (
    '{"type":"subscriptions","channels":'
    '[{"name":"ticker","symbols":["ETHUSD"]}]}'
)
HEARTBEAT = '{"type":"heartbeat"}'
TICKER = '{"type":"ticker","sy":"ETHUSD","sp":"3050.5","ts":1775801092453559}'
MALFORMED = "{not json"
NEW_CHANNEL = '{"type":"brand_new","k":1}'


def client_settings(url: str, **overrides: Any) -> WebSocketSettings:
    """Fast, test-friendly settings for a client."""
    base: dict[str, Any] = dict(
        url=url,
        reconnect_delay=0.05,
        max_retries=10,
        heartbeat_timeout=2.0,
        ping_interval=5.0,
        pong_timeout=1.0,
    )
    base.update(overrides)
    return WebSocketSettings(**base)


async def make_client(server: MockWSServer, **overrides: Any) -> DeltaWebSocketClient:
    """Build a client wired to the mock server with test credentials."""
    return DeltaWebSocketClient(
        client_settings(server.url, **overrides),
        api_key=API_KEY,
        api_secret=API_SECRET,
    )


async def _record(events_list: list[WSEvent], event: WSEvent) -> None:
    events_list.append(event)


def find_received(received: list[str], message_type: str) -> list[dict[str, Any]]:
    """Return parsed received messages of a given ``type``."""
    found: list[dict[str, Any]] = []
    for raw in received:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == message_type:
            found.append(payload)
    return found


@pytest.mark.asyncio
async def test_full_stream_flow() -> None:
    server = MockWSServer(
        script=[
            ("send", AUTH_OK),
            ("send", ACK),
            ("send", HEARTBEAT),
            ("send", TICKER),
            ("send", NEW_CHANNEL),
            ("send", MALFORMED),
        ]
    )
    async with server:
        client = await make_client(server)
        received_events: list[WSEvent] = []
        client.add_listener("*", lambda event: _record(received_events, event))
        client.start()
        await wait_until(
            lambda: any(isinstance(e, events.TickerEvent) for e in received_events)
        )

        await client.subscribe("ticker", ["ETHUSD"])
        await wait_until(lambda: bool(find_received(server.received, "subscribe")))

        assert find_received(server.received, "enable_heartbeat")
        auth_messages = find_received(server.received, "key-auth")
        assert len(auth_messages) == 1
        payload = auth_messages[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["api-key"] == API_KEY
        timestamp = str(payload["timestamp"])
        assert payload["signature"] == sign_key_auth(API_SECRET, timestamp)

        subscribe = find_received(server.received, "subscribe")[0]
        assert subscribe == {
            "type": "subscribe",
            "payload": {
                "channels": [{"name": "ticker", "symbols": ["ETHUSD"]}]
            },
        }

        types = [event.type for event in received_events]
        assert "ticker" in types
        ticker = next(e for e in received_events if isinstance(e, events.TickerEvent))
        assert ticker.sy == "ETHUSD"
        assert ticker.sp == events.Decimal("3050.5")
        assert any(isinstance(e, UnknownWSEvent) for e in received_events)

        assert server.connections == 1
        assert client.is_connected
        await client.close()


@pytest.mark.asyncio
async def test_heartbeat_keeps_connection_alive() -> None:
    server = MockWSServer(
        script=[("send", AUTH_OK)], heartbeat_interval=0.1
    )
    async with server:
        client = await make_client(server, heartbeat_timeout=0.15)
        client.start()
        await wait_until(lambda: server.connections == 1)
        await asyncio.sleep(0.5)
        assert server.connections == 1
        assert client.is_connected
        await client.close()


@pytest.mark.asyncio
async def test_reconnect_reauths_and_resubscribes() -> None:
    script = [
        ("send", AUTH_OK),
        ("send", ACK),
        ("send", TICKER),
        ("wait", 0.1),
        ("close", 1011),
    ]
    server = MockWSServer(script)
    async with server:
        client = await make_client(server)
        await client.subscribe("ticker", ["ETHUSD"])
        client.start()
        await wait_until(lambda: len(find_received(server.received, "key-auth")) >= 2)

        subscribe_messages = find_received(server.received, "subscribe")
        assert len(subscribe_messages) >= 2
        for message in subscribe_messages:
            channels = cast(list[dict[str, Any]], message["payload"]["channels"])
            assert channels[0]["symbols"] == ["ETHUSD"]
        await client.close()


@pytest.mark.asyncio
async def test_auth_failure_retries_connection() -> None:
    server = MockWSServer(script=[("send", AUTH_FAIL)])
    async with server:
        client = await make_client(server, max_retries=3)
        client.start()
        await wait_until(lambda: server.connections >= 2)
        await client.close()


@pytest.mark.asyncio
async def test_subscribe_queued_until_connected() -> None:
    server = MockWSServer(script=[("send", AUTH_OK), ("send", ACK)])
    async with server:
        client = await make_client(server)
        await client.subscribe("ticker", ["ETHUSD"])
        assert find_received(server.received, "subscribe") == []
        client.start()
        await wait_until(lambda: bool(find_received(server.received, "subscribe")))
        await client.close()


@pytest.mark.asyncio
async def test_unsubscribe_sends_payload() -> None:
    server = MockWSServer(script=[("send", AUTH_OK), ("send", ACK)])
    async with server:
        client = await make_client(server)
        client.start()
        await wait_until(lambda: server.connections == 1)
        await client.subscribe("ticker", ["ETHUSD"])
        await wait_until(lambda: bool(find_received(server.received, "subscribe")))
        await client.unsubscribe("ticker", ["ETHUSD"])
        await wait_until(lambda: bool(find_received(server.received, "unsubscribe")))
        unsubscribe = find_received(server.received, "unsubscribe")
        assert unsubscribe[0]["payload"]["channels"][0]["name"] == "ticker"
        assert client.subscriptions == {}
        await client.close()


def test_credentials_required() -> None:
    settings = WebSocketSettings(url="ws://127.0.0.1:1")
    with pytest.raises(AuthenticationError, match="credentials"):
        DeltaWebSocketClient(settings, api_key="", api_secret="")
    with pytest.raises(AuthenticationError, match="credentials"):
        DeltaWebSocketClient(settings, api_key="only-key", api_secret="")
