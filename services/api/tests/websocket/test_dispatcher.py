"""Tests for the WebSocket event dispatcher."""

import asyncio

import pytest

from app.ws.dispatcher import EventDispatcher
from app.ws.models import WSEvent


class TickerEvent(WSEvent):
    sy: str


class TradeEvent(WSEvent):
    sy: str


def make_ticker() -> TickerEvent:
    return TickerEvent(type="ticker", sy="BTCUSD")


@pytest.mark.asyncio
async def test_exact_channel_routing() -> None:
    dispatcher = EventDispatcher()
    received: list[WSEvent] = []

    async def on_ticker(event: WSEvent) -> None:
        received.append(event)

    async def on_trade(event: WSEvent) -> None:
        received.append(event)

    dispatcher.add_listener("ticker", on_ticker)
    dispatcher.add_listener("trades", on_trade)
    dispatcher.emit(make_ticker())
    await asyncio.sleep(0.01)
    assert [event.type for event in received] == ["ticker"]


@pytest.mark.asyncio
async def test_wildcard_receives_everything() -> None:
    dispatcher = EventDispatcher()
    received: list[WSEvent] = []

    async def on_all(event: WSEvent) -> None:
        received.append(event)

    dispatcher.add_listener("*", on_all)
    dispatcher.emit(make_ticker())
    dispatcher.emit(TradeEvent(type="trades", sy="ETHUSD"))
    await asyncio.sleep(0.01)
    assert [event.type for event in received] == ["ticker", "trades"]


@pytest.mark.asyncio
async def test_remove_listener() -> None:
    dispatcher = EventDispatcher()
    received: list[WSEvent] = []

    async def on_ticker(event: WSEvent) -> None:
        received.append(event)

    dispatcher.add_listener("ticker", on_ticker)
    assert dispatcher.remove_listener("ticker", on_ticker)
    assert not dispatcher.remove_listener("ticker", on_ticker)
    assert not dispatcher.remove_listener("unknown", on_ticker)
    dispatcher.emit(make_ticker())
    await asyncio.sleep(0.01)
    assert received == []


@pytest.mark.asyncio
async def test_raising_listener_does_not_block_others() -> None:
    dispatcher = EventDispatcher()
    received: list[WSEvent] = []

    async def on_bad(event: WSEvent) -> None:
        raise RuntimeError("listener bug")

    async def on_good(event: WSEvent) -> None:
        received.append(event)

    dispatcher.add_listener("ticker", on_bad)
    dispatcher.add_listener("ticker", on_good)
    dispatcher.emit(make_ticker())
    await asyncio.sleep(0.01)
    assert [event.type for event in received] == ["ticker"]
