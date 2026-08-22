"""End-to-end and stage tests for the market data pipeline."""

import json
import logging
from datetime import UTC
from decimal import Decimal
from typing import Any

import pytest

from app.events import EventBus
from app.integrations.delta.websocket.models import TradesEvent
from app.marketdata import (
    MarketDataPipeline,
)
from app.marketdata.normalizer import DeltaNormalizer

VALID_TRADE = json.dumps(
    {
        "type": "trades",
        "p": "72141.5",
        "r": "t",
        "s": "1.5",
        "sy": "BTCUSD",
        "t": 1700000000000000,
        "ts": 1700000000005000,
    }
)

VALID_TICKER = json.dumps(
    {
        "type": "ticker",
        "ts": 1700000000000000,
        "d": [
            {
                "s": "XRPUSD",
                "m": "0.5256",
                "m24hc": "1.59",
                "ohlc": ["0.51", "0.55", "0.49", "0.54"],
                "oi": ["100", "5"],
                "q": ["0.53", "10", "0.52", "20", None],
                "to": ["1000", "1000"],
            },
            {
                "s": "ETH-200426",
                "q": ["3401", "2", "3399", "3", None],
            },
        ],
    }
)

VALID_ORDER_BOOK = json.dumps(
    {
        "type": "ob_updates",
        "action": "snapshot",
        "a": [["16919.0", "1087"], ["16919.5", "1193"]],
        "b": [["16918.0", "602"]],
        "ts": 1671140718980723,
        "seq": 6199,
        "sy": "BTCUSD",
        "cs": 2178756498,
    }
)


class Collector:
    """Async handler that records every received event."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def __call__(self, event: Any) -> None:
        self.events.append(event)


def make_pipeline(bus: EventBus) -> MarketDataPipeline:
    return MarketDataPipeline(normalizer=DeltaNormalizer(), bus=bus)


@pytest.mark.asyncio
async def test_valid_trade_reaches_bus() -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TradeEventReceived", collector)

    pipeline = make_pipeline(bus)
    await pipeline.process_raw(VALID_TRADE)
    await bus.drain()

    assert len(collector.events) == 1
    event = collector.events[0]
    assert event.event_type == "TradeEventReceived"
    assert event.source == "delta.ws"
    assert event.timestamp.tzinfo == UTC
    trade = event.trade
    assert trade.exchange == "delta"
    assert trade.symbol == "BTCUSD"
    assert trade.price == Decimal("72141.5")
    assert trade.size == Decimal("1.5")
    assert trade.side == "buy"
    metrics = pipeline.metrics.snapshot()
    assert metrics["messages_received"] == 1
    assert metrics["messages_normalized"] == 1
    assert metrics["events_published"] == 1
    assert metrics["validation_failures"] == 0
    assert metrics["average_latency_ms"] is not None


@pytest.mark.asyncio
async def test_valid_ticker_expands_to_multiple_events() -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TickerUpdated", collector)

    pipeline = make_pipeline(bus)
    await pipeline.process_raw(VALID_TICKER)
    await bus.drain()

    assert len(collector.events) == 2
    assert [event.ticker.symbol for event in collector.events] == [
        "XRPUSD",
        "ETH-200426",
    ]
    assert collector.events[0].ticker.bid == Decimal("0.52")
    assert collector.events[1].ticker.ask == Decimal("3401")
    metrics = pipeline.metrics.snapshot()
    assert metrics["messages_normalized"] == 2
    assert metrics["events_published"] == 2


@pytest.mark.asyncio
async def test_valid_order_book_reaches_bus() -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("OrderBookUpdated", collector)

    pipeline = make_pipeline(bus)
    await pipeline.process_raw(VALID_ORDER_BOOK)
    await bus.drain()

    assert len(collector.events) == 1
    book = collector.events[0].order_book
    assert book.exchange == "delta"
    assert book.symbol == "BTCUSD"
    assert book.kind == "full"
    assert book.is_snapshot is True
    assert book.sequence == 6199
    assert len(book.asks) == 2
    assert len(book.bids) == 1


@pytest.mark.asyncio
async def test_malformed_json_is_rejected_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TradeEventReceived", collector)

    pipeline = make_pipeline(bus)
    with caplog.at_level(logging.WARNING, logger="app.marketdata"):
        await pipeline.process_raw("{not json")

    assert collector.events == []
    metrics = pipeline.metrics.snapshot()
    assert metrics["messages_received"] == 1
    assert metrics["validation_failures"] == 1
    assert "rejected" in caplog.text


@pytest.mark.asyncio
async def test_missing_fields_are_rejected() -> None:
    bus = EventBus()
    pipeline = make_pipeline(bus)
    raw = json.dumps({"type": "trades", "sy": "BTCUSD"})

    await pipeline.process_raw(raw)

    assert pipeline.metrics.snapshot()["validation_failures"] == 1


@pytest.mark.asyncio
async def test_invalid_numeric_values_are_rejected_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TradeEventReceived", collector)

    pipeline = make_pipeline(bus)
    raw = json.dumps(
        {
            "type": "trades",
            "p": "-5",
            "r": "t",
            "s": "1.5",
            "sy": "BTCUSD",
            "t": 1700000000000000,
            "ts": 1700000000005000,
        }
    )
    with caplog.at_level(logging.WARNING, logger="app.marketdata"):
        await pipeline.process_raw(raw)

    assert collector.events == []
    metrics = pipeline.metrics.snapshot()
    assert metrics["validation_failures"] == 1
    assert "price" in caplog.text


@pytest.mark.asyncio
async def test_unsupported_message_types_are_counted_not_published() -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TradeEventReceived", collector)

    pipeline = make_pipeline(bus)
    raw = json.dumps(
        {"type": "mark_price", "p": "72124.5", "sy": "MARK:BTCUSD", "ts": 1700000000000000}
    )
    await pipeline.process_raw(raw)

    assert collector.events == []
    metrics = pipeline.metrics.snapshot()
    assert metrics["unsupported_messages"] == 1
    assert metrics["validation_failures"] == 0
    assert metrics["events_published"] == 0


@pytest.mark.asyncio
async def test_heartbeat_is_ignored_silently() -> None:
    bus = EventBus()
    pipeline = make_pipeline(bus)

    await pipeline.process_raw('{"type": "heartbeat"}')

    metrics = pipeline.metrics.snapshot()
    assert metrics["messages_received"] == 1
    assert metrics["validation_failures"] == 0
    assert metrics["unsupported_messages"] == 0
    assert metrics["events_published"] == 0


@pytest.mark.asyncio
async def test_handle_skips_parsing_for_client_wiring() -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TradeEventReceived", collector)

    pipeline = make_pipeline(bus)
    message = TradesEvent(
        type="trades",
        p=Decimal("72141.5"),
        r="t",
        s=Decimal("1.5"),
        sy="BTCUSD",
        t=1700000000000000,
        ts=1700000000005000,
    )
    await pipeline.handle(message)
    await bus.drain()

    assert len(collector.events) == 1
    metrics = pipeline.metrics.snapshot()
    assert metrics["messages_received"] == 1
    assert metrics["messages_normalized"] == 1
    assert metrics["events_published"] == 1


@pytest.mark.asyncio
async def test_bus_event_payload_contains_domain_data() -> None:
    bus = EventBus()
    collector = Collector()
    bus.subscribe("TradeEventReceived", collector)

    pipeline = make_pipeline(bus)
    await pipeline.process_raw(VALID_TRADE)
    await bus.drain()

    payload = collector.events[0].payload
    assert payload["trade"]["symbol"] == "BTCUSD"
    assert payload["trade"]["exchange"] == "delta"
