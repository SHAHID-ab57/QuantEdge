"""Unit tests for the market state snapshot model."""

from datetime import UTC, datetime
from decimal import Decimal

from app.events.example_events import CandleClosed
from app.marketdata.models import OrderBookEvent, OrderBookLevel, TickerEvent, TradeEvent
from app.state.models import MarketState

EVENT_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _trade(price: Decimal) -> TradeEvent:
    return TradeEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=EVENT_TIME,
        side="buy",
        price=price,
        size=Decimal("1"),
    )


def _ticker(last_price: Decimal | None = None, mark: Decimal | None = None) -> TickerEvent:
    return TickerEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=EVENT_TIME,
        last_price=last_price,
        mark_price=mark,
    )


def _candle() -> CandleClosed:
    return CandleClosed(
        source="test",
        symbol="ETHUSD",
        resolution="1h",
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("10"),
    )


def test_last_price_prefers_trade() -> None:
    """A trade price beats every ticker price."""
    state = MarketState(
        symbol="ETHUSD",
        updated_at=EVENT_TIME,
        trade=_trade(Decimal("3010")),
        ticker=_ticker(last_price=Decimal("3000"), mark=Decimal("2990")),
    )
    assert state.last_price == Decimal("3010")


def test_last_price_falls_back_to_ticker_last() -> None:
    """Without a trade, the ticker last price wins over the mark price."""
    state = MarketState(
        symbol="ETHUSD",
        updated_at=EVENT_TIME,
        ticker=_ticker(last_price=Decimal("3000"), mark=Decimal("2990")),
    )
    assert state.last_price == Decimal("3000")


def test_last_price_falls_back_to_ticker_mark() -> None:
    """Without a last price, the mark price is used."""
    state = MarketState(
        symbol="ETHUSD",
        updated_at=EVENT_TIME,
        ticker=_ticker(mark=Decimal("2990")),
    )
    assert state.last_price == Decimal("2990")


def test_last_price_none_without_quotes() -> None:
    """No trade and no ticker prices means no last price."""
    state = MarketState(symbol="ETHUSD", updated_at=EVENT_TIME, ticker=_ticker())
    assert state.last_price is None


def test_state_carries_all_slots() -> None:
    """Every slot holds the last-seen domain object."""
    order_book = OrderBookEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=EVENT_TIME,
        kind="l2",
        bids=[OrderBookLevel(price=Decimal("100"), size=Decimal("5"))],
        asks=[OrderBookLevel(price=Decimal("101"), size=Decimal("6"))],
        is_snapshot=True,
    )
    state = MarketState(
        symbol="ETHUSD",
        updated_at=EVENT_TIME,
        trade=_trade(Decimal("100.5")),
        ticker=_ticker(last_price=Decimal("100.5")),
        candle=_candle(),
        order_book=order_book,
    )
    assert state.trade is not None
    assert state.ticker is not None
    assert state.candle is not None
    assert state.order_book is order_book
