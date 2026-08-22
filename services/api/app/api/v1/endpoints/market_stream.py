"""Live market data WebSocket gateway for browser clients.

This is the only real-time channel the dashboard uses: it relays trade,
ticker, and reconstructed order-book events already flowing through the
in-process event bus (published by the Delta WebSocket client +
processing pipeline, see ``app.runtime``) to subscribed browser
connections. The frontend never opens a connection to the exchange
itself.

Protocol (JSON text frames):

Client -> server:
    ``{"action": "subscribe", "symbols": ["ETHUSD"]}``
    ``{"action": "unsubscribe", "symbols": ["ETHUSD"]}``
    ``{"action": "ping"}``

Server -> client:
    ``{"type": "snapshot", "symbol": "ETHUSD",
    "trade": {...}|null, "ticker": {...}|null, "orderbook": {...}|null}``
    ``{"type": "trade", "symbol": "ETHUSD", "data": {...}}``
    ``{"type": "ticker", "symbol": "ETHUSD", "data": {...}}``
    ``{"type": "orderbook", "symbol": "ETHUSD",
    "data": {"bids": [...], "asks": [...], "event_time", "sequence"}}``
    ``{"type": "pong"}``
    ``{"type": "error", "detail": "..."}``

``orderbook.bids``/``asks`` are already sorted (bids descending, asks
ascending) and depth-limited by the gateway — see
``app.marketdata.gateway``'s ``_ORDERBOOK_DEPTH`` — and reflect a
*reconstructed* book (snapshot + merged incremental diffs via
``app.marketdata.orderbook.OrderBookAggregator``), not a single raw
exchange message.

No authentication, no trading, no order *execution* data — this is a
read-only market-data relay (order *book* depth included), matching the
rest of the v1 API surface.
"""

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.marketdata.gateway import ConnectionHandle
from app.runtime import Runtime, get_runtime

logger = logging.getLogger("app.api.market_stream")

router = APIRouter(tags=["market-stream"])

RuntimeDep = Annotated[Runtime, Depends(get_runtime)]

_MAX_SYMBOLS_PER_MESSAGE = 20
_KNOWN_ACTIONS = frozenset({"subscribe", "unsubscribe", "ping"})


class ClientMessage(BaseModel):
    """One inbound control message."""

    action: str
    symbols: list[str] = []


async def _writer_loop(websocket: WebSocket, handle: ConnectionHandle) -> None:
    """Drain ``handle``'s queue and send each message to the client.

    A dedicated writer task per connection is what lets the event-bus
    fan-out (a different task) enqueue messages safely — only this loop
    ever calls ``websocket.send_json``, so concurrent sends can never
    interleave on the wire.
    """
    while True:
        message = await handle.queue.get()
        await websocket.send_json(message)


async def _handle_client_message(
    runtime: Runtime, handle: ConnectionHandle, websocket: WebSocket, raw: Any
) -> None:
    try:
        message = ClientMessage.model_validate(raw)
    except ValidationError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        return

    if message.action not in _KNOWN_ACTIONS:
        await websocket.send_json({"type": "error", "detail": f"unknown action '{message.action}'"})
        return

    symbols = message.symbols[:_MAX_SYMBOLS_PER_MESSAGE]
    if message.action == "subscribe":
        runtime.gateway.subscribe(handle, symbols)
    elif message.action == "unsubscribe":
        runtime.gateway.unsubscribe(handle, symbols)
    elif message.action == "ping":
        await websocket.send_json({"type": "pong"})


@router.websocket("/ws/market")
async def market_stream(websocket: WebSocket, runtime: RuntimeDep) -> None:
    """Accept a browser connection and relay live market data on demand.

    A client must send a ``subscribe`` message to receive anything; no
    symbol is implicitly subscribed on connect.
    """
    await websocket.accept()
    handle = runtime.gateway.register()
    writer_task = asyncio.create_task(_writer_loop(websocket, handle))
    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                raw = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid JSON"})
                continue
            await _handle_client_message(runtime, handle, websocket, raw)
    except WebSocketDisconnect:
        logger.debug("market_stream client disconnected")
    except Exception:
        logger.exception("market_stream connection failed")
    finally:
        writer_task.cancel()
        runtime.gateway.unregister(handle)
