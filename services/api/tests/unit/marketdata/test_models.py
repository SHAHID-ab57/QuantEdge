"""Tests for the exchange-independent market data domain models."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.marketdata.models import (
    OrderBookEvent,
    OrderBookLevel,
    TickerEvent,
    TradeEvent,
)


def test_trade_event_defaults_and_fields() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    trade = TradeEvent(
        exchange="delta",
        symbol="BTCUSD",
        event_time=event_time,
        price=Decimal("72141.5"),
        size=Decimal("1.5"),
        side="unknown",
    )
    assert trade.exchange == "delta"
    assert trade.symbol == "BTCUSD"
    assert trade.event_time == event_time
    assert trade.received_time.tzinfo == UTC
    assert trade.sequence is None
    assert trade.trade_time is None


def test_trade_event_accepts_side() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    trade = TradeEvent(
        exchange="delta",
        symbol="BTCUSD",
        event_time=event_time,
        price=Decimal("1"),
        size=Decimal("2"),
        side="buy",
    )
    assert trade.side == "buy"


@pytest.mark.parametrize(
    "price, size",
    [
        (Decimal("0"), Decimal("1")),
        (Decimal("-1"), Decimal("1")),
        (Decimal("1"), Decimal("0")),
        (Decimal("1"), Decimal("-1")),
    ],
)
def test_trade_rejects_non_positive_price_or_size(price: Decimal, size: Decimal) -> None:
    with pytest.raises(ValidationError):
        TradeEvent(
            exchange="delta",
            symbol="BTCUSD",
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            price=price,
            size=size,
            side="buy",
        )


def test_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        TradeEvent(
            exchange="delta",
            symbol="BTCUSD",
            event_time=datetime(2026, 1, 2, 3, 4, 5),
            price=Decimal("1"),
            size=Decimal("2"),
            side="buy",
        )


@pytest.mark.parametrize(
    "symbol",
    ["BTCUSD", "MARK:BTCUSD", ".DEXBTUSD", "BTC-310326", "ETH-200426"],
)
def test_symbol_pattern_accepts_known_formats(symbol: str) -> None:
    TradeEvent(
        exchange="delta",
        symbol=symbol,
        event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        price=Decimal("1"),
        size=Decimal("2"),
        side="buy",
    )


@pytest.mark.parametrize("symbol", ["", "BAD SYMBOL!", "btcusd", "symbol/"])
def test_symbol_pattern_rejects_invalid(symbol: str) -> None:
    with pytest.raises(ValidationError):
        TradeEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            price=Decimal("1"),
            size=Decimal("2"),
            side="buy",
        )


def test_ticker_defaults_and_negative_bid_rejected() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    ticker = TickerEvent(exchange="delta", symbol="BTCUSD", event_time=event_time)
    assert ticker.bid is None
    assert ticker.ask is None
    assert ticker.last_price is None
    assert ticker.price_change_24h is None
    assert ticker.sequence is None
    with pytest.raises(ValidationError):
        TickerEvent(
            exchange="delta",
            symbol="BTCUSD",
            event_time=event_time,
            bid=Decimal("-1"),
        )


def test_ticker_allows_negative_price_change() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    ticker = TickerEvent(
        exchange="delta",
        symbol="BTCUSD",
        event_time=event_time,
        price_change_24h=Decimal("-1.5"),
    )
    assert ticker.price_change_24h == Decimal("-1.5")


def test_order_book_levels_validation() -> None:
    OrderBookLevel(price=Decimal("72141.5"), size=Decimal("0"))
    with pytest.raises(ValidationError):
        OrderBookLevel(price=Decimal("0"), size=Decimal("1"))
    with pytest.raises(ValidationError):
        OrderBookLevel(price=Decimal("72141.5"), size=Decimal("-1"))


def test_order_book_event_defaults() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    book = OrderBookEvent(exchange="delta", symbol="BTCUSD", event_time=event_time, kind="l2")
    assert book.bids == []
    assert book.asks == []
    assert book.is_snapshot is True
    assert book.sequence is None


def test_order_book_rejects_unknown_kind_and_extra_fields() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    with pytest.raises(ValidationError):
        OrderBookEvent.model_validate(
            {
                "exchange": "delta",
                "symbol": "BTCUSD",
                "event_time": event_time,
                "kind": "top",
            }
        )
    with pytest.raises(ValidationError):
        OrderBookEvent.model_validate(
            {
                "exchange": "delta",
                "symbol": "BTCUSD",
                "event_time": event_time,
                "kind": "l1",
                "nope": True,
            }
        )
