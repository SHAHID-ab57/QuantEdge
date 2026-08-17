"""Tests for the example events and handlers."""

import logging
from datetime import UTC
from decimal import Decimal

import pytest

from app.events import (
    CandleClosed,
    DebugHandler,
    EventBus,
    LoggingHandler,
    MarketTradeReceived,
    OrderBookUpdated,
)


def test_market_trade_received() -> None:
    event = MarketTradeReceived(
        source="delta.ws",
        symbol="BTCUSD",
        price=Decimal("72141.5"),
        size=Decimal("1.5"),
        side="buy",
    )
    assert event.event_type == "MarketTradeReceived"
    assert event.timestamp.tzinfo == UTC
    assert event.payload == {
        "symbol": "BTCUSD",
        "price": Decimal("72141.5"),
        "size": Decimal("1.5"),
        "side": "buy",
    }


def test_candle_closed() -> None:
    event = CandleClosed(
        source="delta.ws",
        symbol="BTCUSD",
        resolution="1h",
        open=Decimal("71000"),
        high=Decimal("72141.5"),
        low=Decimal("70950"),
        close=Decimal("72000"),
        volume=Decimal("1234.5"),
    )
    assert event.event_type == "CandleClosed"
    assert event.payload["resolution"] == "1h"
    assert event.payload["volume"] == Decimal("1234.5")


def test_order_book_updated() -> None:
    event = OrderBookUpdated(
        source="delta.ws",
        symbol="BTCUSD",
        asks=[(Decimal("72142.0"), Decimal("3.0"))],
        bids=[(Decimal("72141.5"), Decimal("2.5"))],
    )
    assert event.event_type == "OrderBookUpdated"
    assert event.payload["asks"] == [(Decimal("72142.0"), Decimal("3.0"))]
    assert event.payload["bids"] == [(Decimal("72141.5"), Decimal("2.5"))]


@pytest.mark.asyncio
async def test_logging_handler_logs_summary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    bus.subscribe("MarketTradeReceived", LoggingHandler())
    event = MarketTradeReceived(
        source="delta.ws",
        symbol="BTCUSD",
        price=Decimal("1"),
        size=Decimal("2"),
        side="sell",
    )
    with caplog.at_level(logging.INFO, logger="app.events"):
        await bus.publish(event)
        await bus.drain()
    assert any(
        "Event received" in record.message
        and "MarketTradeReceived" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_debug_handler_logs_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    bus.subscribe("MarketTradeReceived", DebugHandler())
    event = MarketTradeReceived(
        source="delta.ws",
        symbol="BTCUSD",
        price=Decimal("1"),
        size=Decimal("2"),
        side="buy",
    )
    with caplog.at_level(logging.DEBUG, logger="app.events"):
        await bus.publish(event)
        await bus.drain()
    assert any(
        "Event payload" in record.message and "BTCUSD" in record.message
        for record in caplog.records
    )