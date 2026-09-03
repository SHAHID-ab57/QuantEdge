"""Tests for the market state manager."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from app.events import CandleClosed, Event, EventBus
from app.marketdata import (
    MarketDataPipeline,
    OrderBookUpdated,
    TickerUpdated,
    TradeEventReceived,
)
from app.marketdata.models import OrderBookEvent, TickerEvent, TradeEvent
from app.marketdata.normalizer import DeltaNormalizer
from app.state import MarketState, MarketStateManager


def make_trade_event(symbol: str = "BTCUSD", price: str = "72141.5") -> TradeEventReceived:
    return TradeEventReceived(
        source="delta.ws",
        trade=TradeEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            price=Decimal(price),
            size=Decimal("1.5"),
            side="unknown",
        ),
    )


def make_ticker_event(symbol: str = "BTCUSD", bid: str = "72141.0") -> TickerUpdated:
    return TickerUpdated(
        source="delta.ws",
        ticker=TickerEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            bid=Decimal(bid),
        ),
    )


def make_book_event(symbol: str = "BTCUSD") -> OrderBookUpdated:
    return OrderBookUpdated(
        source="delta.ws",
        order_book=OrderBookEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            kind="l1",
            bids=[],
            asks=[],
        ),
    )


def make_candle_event(symbol: str = "BTCUSD", resolution: str = "1h") -> CandleClosed:
    return CandleClosed(
        source="delta.ws",
        symbol=symbol,
        resolution=resolution,
        open=Decimal("71000"),
        high=Decimal("72000"),
        low=Decimal("70900"),
        close=Decimal("71500"),
        volume=Decimal("100"),
    )


async def publish_all(bus: EventBus, events: list[Event]) -> None:
    for event in events:
        await bus.publish(event)
    await bus.drain()


def latest_trade(manager: MarketStateManager, symbol: str) -> TradeEvent:
    trade = manager.get_latest_trade(symbol)
    assert trade is not None
    return trade


def latest_ticker(manager: MarketStateManager, symbol: str) -> TickerEvent:
    ticker = manager.get_latest_ticker(symbol)
    assert ticker is not None
    return ticker


def latest_candle(
    manager: MarketStateManager, symbol: str, resolution: str | None = None
) -> CandleClosed:
    candle = manager.get_latest_candle(symbol, resolution)
    assert candle is not None
    return candle


def latest_book(manager: MarketStateManager, symbol: str) -> OrderBookEvent:
    book = manager.get_order_book(symbol)
    assert book is not None
    return book


def market_state(manager: MarketStateManager, symbol: str) -> MarketState:
    state = manager.get_market_state(symbol)
    assert state is not None
    return state


@pytest.mark.asyncio
async def test_updates_and_queries_round_trip() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    await publish_all(
        bus,
        [make_trade_event(), make_ticker_event(), make_book_event(), make_candle_event()],
    )

    assert latest_trade(manager, "BTCUSD").price == Decimal("72141.5")
    assert latest_ticker(manager, "BTCUSD").bid == Decimal("72141.0")
    assert latest_candle(manager, "BTCUSD").close == Decimal("71500")
    assert latest_candle(manager, "BTCUSD", "1h").resolution == "1h"
    assert latest_book(manager, "BTCUSD").kind == "l1"
    assert manager.symbols() == frozenset({"BTCUSD"})


@pytest.mark.asyncio
async def test_multiple_symbols_are_isolated() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    await publish_all(
        bus,
        [
            make_trade_event("BTCUSD", "72141.5"),
            make_trade_event("ETHUSD", "3400.5"),
            make_candle_event("BTCUSD", "1h"),
            make_candle_event("ETHUSD", "5m"),
        ],
    )

    assert latest_trade(manager, "BTCUSD").price == Decimal("72141.5")
    assert latest_trade(manager, "ETHUSD").price == Decimal("3400.5")
    assert latest_candle(manager, "ETHUSD", "5m").resolution == "5m"
    assert market_state(manager, "BTCUSD").candle is not None
    assert market_state(manager, "ETHUSD").trade is not None
    assert manager.symbols() == frozenset({"BTCUSD", "ETHUSD"})


@pytest.mark.asyncio
async def test_state_replacement() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    await publish_all(bus, [make_trade_event("BTCUSD", "72141.5")])
    first = manager.get_latest_trade("BTCUSD")
    await publish_all(bus, [make_trade_event("BTCUSD", "72200.0")])
    second = manager.get_latest_trade("BTCUSD")

    assert first is not None
    assert first is not second
    assert second is not None
    assert second.price == Decimal("72200.0")
    assert manager.metrics.snapshot()["state_updates"] == 2


@pytest.mark.asyncio
async def test_candles_are_keyed_per_resolution() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    await publish_all(
        bus,
        [make_candle_event("BTCUSD", "1h"), make_candle_event("BTCUSD", "5m")],
    )

    assert latest_candle(manager, "BTCUSD", "1h").resolution == "1h"
    assert latest_candle(manager, "BTCUSD", "5m").resolution == "5m"
    assert latest_candle(manager, "BTCUSD").resolution == "5m"


@pytest.mark.asyncio
async def test_invalid_events_are_rejected() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    await publish_all(bus, [make_trade_event("BTCUSD")])
    before = manager.metrics.snapshot()

    bogus = Event(source="delta.ws", event_type="TradeEventReceived")
    await publish_all(bus, [bogus])

    metrics = manager.metrics.snapshot()
    invalid_before = cast(int, before["invalid_events"])
    updates_before = cast(int, before["state_updates"])
    assert metrics["invalid_events"] == invalid_before + 1
    assert metrics["state_updates"] == updates_before
    assert manager.get_latest_trade("BTCUSD") is not None


@pytest.mark.asyncio
async def test_missing_symbols_return_none() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    assert manager.get_latest_trade("DOGEUSD") is None
    assert manager.get_latest_ticker("DOGEUSD") is None
    assert manager.get_latest_candle("DOGEUSD") is None
    assert manager.get_latest_candle("DOGEUSD", resolution="1h") is None
    assert manager.get_order_book("DOGEUSD") is None
    assert manager.get_market_state("DOGEUSD") is None
    assert manager.symbols() == frozenset()
    metrics = manager.metrics.snapshot()
    assert metrics["cache_hits"] == 0
    assert metrics["cache_misses"] == 6


@pytest.mark.asyncio
async def test_concurrent_updates_are_consistent() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)

    async def publisher(symbol: str, start: int, count: int) -> None:
        for i in range(count):
            await bus.publish(make_trade_event(symbol, str(start + i)))

    tasks = [
        asyncio.create_task(publisher("BTCUSD", 70000, 20)),
        asyncio.create_task(publisher("ETHUSD", 3000, 20)),
        asyncio.create_task(publisher("XRPUSD", 2, 20)),
    ]
    await asyncio.gather(*tasks)
    await bus.drain()

    assert latest_trade(manager, "BTCUSD").price == Decimal("70019")
    assert latest_trade(manager, "ETHUSD").price == Decimal("3019")
    assert latest_trade(manager, "XRPUSD").price == Decimal("21")
    metrics = manager.metrics.snapshot()
    assert metrics["state_updates"] == 60
    assert metrics["symbols_tracked"] == 3


@pytest.mark.asyncio
async def test_pipeline_to_manager_end_to_end() -> None:
    bus = EventBus()
    manager = MarketStateManager().attach(bus)
    pipeline = MarketDataPipeline(normalizer=DeltaNormalizer(), bus=bus)

    raw = (
        '{"type":"trades","p":"72141.5","r":"t","s":"1.5","sy":"BTCUSD",'
        '"t":1700000000000000,"ts":1700000000005000}'
    )
    await pipeline.process_raw(raw)
    await bus.drain()

    assert latest_trade(manager, "BTCUSD").price == Decimal("72141.5")
    state = market_state(manager, "BTCUSD")
    assert state.trade is not None
    assert state.updated_at.tzinfo == UTC
    assert state.last_price == Decimal("72141.5")
