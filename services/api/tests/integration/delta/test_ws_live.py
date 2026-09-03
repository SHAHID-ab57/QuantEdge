"""Live integration test for the Delta public WebSocket endpoint.

Connects to the real public socket (no credentials), subscribes to the
``ticker`` channel, and verifies that live ticker messages arrive.

Run with:
    uv run pytest -m integration --run-integration \
        tests/integrations/delta/test_ws_live.py
"""

import asyncio

import pytest

from app.integrations.delta.websocket import models as events
from app.integrations.delta.websocket.client import DeltaWebSocketClient
from app.ws.config import WebSocketSettings
from app.ws.models import WSEvent

pytestmark = pytest.mark.integration

PUBLIC_SOCKET = "wss://public-socket.india.delta.exchange"


async def _record(events_list: list[WSEvent], event: WSEvent) -> None:
    events_list.append(event)


@pytest.mark.asyncio
async def test_public_ticker_stream_receives_live_messages() -> None:
    settings = WebSocketSettings(
        url=PUBLIC_SOCKET,
        reconnect_delay=1.0,
        max_retries=3,
        heartbeat_timeout=35.0,
    )
    client = DeltaWebSocketClient(settings, public=True)
    received: list[WSEvent] = []
    client.add_listener("ticker", lambda event: _record(received, event))
    await client.subscribe("ticker", ["BTCUSD"])
    client.start()

    try:
        deadline = asyncio.get_running_loop().time() + 20.0
        while asyncio.get_running_loop().time() < deadline:
            tickers = [e for e in received if isinstance(e, events.TickerEvent)]
            if tickers:
                ticker = tickers[0]
                assert ticker.sy == "BTCUSD"
                assert ticker.ts is not None
                assert any(product.s == "BTCUSD" for product in (ticker.d or []))
                return
            await asyncio.sleep(0.1)
        pytest.fail("no live ticker message received within 20s")
    finally:
        await client.close()
