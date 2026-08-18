"""Tests for the Delta -> domain normalizer."""

from decimal import Decimal
from typing import cast

from app.integrations.delta.websocket.models import (
    HeartbeatEvent,
    MarkPriceEvent,
    OrderBookL1Event,
    OrderBookL2Event,
    OrderBookUpdatesEvent,
    SystemStatusEvent,
    TickerData,
    TradesEvent,
    utc_from_micros,
)
from app.integrations.delta.websocket.models import (
    TickerEvent as DeltaTickerEvent,
)
from app.marketdata.models import OrderBookEvent, TickerEvent, TradeEvent
from app.marketdata.normalizer import DeltaNormalizer
from app.ws.models import UnknownWSEvent


def test_trades_normalize_to_trade_event() -> None:
    message = TradesEvent(
        type="trades",
        p=Decimal("72141.5"),
        r="t",
        s=Decimal("1.5"),
        sy="BTCUSD",
        t=1700000000000000,
        ts=1700000000005000,
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    trade = cast(TradeEvent, result.events[0])
    assert trade.exchange == "delta"
    assert trade.symbol == "BTCUSD"
    assert trade.price == Decimal("72141.5")
    assert trade.size == Decimal("1.5")
    assert trade.side == "unknown"
    assert trade.event_time == utc_from_micros(1700000000005000)
    assert trade.trade_time == utc_from_micros(1700000000000000)
    assert trade.sequence is None


def test_ticker_d_array_expands_to_one_event_per_product() -> None:
    message = DeltaTickerEvent(
        type="ticker",
        ts=1700000000000000,
        d=[
            TickerData(
                s="XRPUSD",
                i=27,
                m=Decimal("0.5256"),
                m24hc=Decimal("1.59"),
                ohlc=[Decimal("0.51"), Decimal("0.55"), Decimal("0.49"), Decimal("0.54")],
                oi=[Decimal("100"), Decimal("5")],
                q=[Decimal("0.53"), Decimal("10"), Decimal("0.52"), Decimal("20"), None],
                to=[Decimal("1000"), Decimal("1000")],
            ),
            TickerData(
                s="ETH-200426",
                m=Decimal("3400"),
                q=[Decimal("3401"), Decimal("2"), Decimal("3399"), Decimal("3"), None],
            ),
        ],
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    assert len(result.events) == 2
    first = cast(TickerEvent, result.events[0])
    second = cast(TickerEvent, result.events[1])
    assert first.symbol == "XRPUSD"
    assert first.event_time == utc_from_micros(1700000000000000)
    assert first.bid == Decimal("0.52")
    assert first.bid_size == Decimal("20")
    assert first.ask == Decimal("0.53")
    assert first.ask_size == Decimal("10")
    assert first.last_price == Decimal("0.54")
    assert first.mark_price == Decimal("0.5256")
    assert first.open_interest == Decimal("100")
    assert first.price_change_24h == Decimal("1.59")
    assert first.turnover == Decimal("1000")
    assert second.symbol == "ETH-200426"
    assert second.spot_price is None


def test_ticker_single_symbol_form() -> None:
    message = DeltaTickerEvent(
        type="ticker",
        sy="BTCUSD",
        sp=Decimal("72100.5"),
        ts=1700000000000000,
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    ticker = cast(TickerEvent, result.events[0])
    assert ticker.symbol == "BTCUSD"
    assert ticker.spot_price == Decimal("72100.5")
    assert ticker.bid is None


def test_order_book_l1_normalizes() -> None:
    message = OrderBookL1Event.model_validate(
        {
            "type": "ob_l1",
            "ap": "72142.0",
            "as": "3.0",
            "bp": "72141.5",
            "bs": "2.5",
            "lts": 1700000000000000,
            "sy": "BTCUSD",
            "ts": 1700000000005000,
        }
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    book = cast(OrderBookEvent, result.events[0])
    assert book.kind == "l1"
    assert book.is_snapshot is True
    assert book.sequence is None
    assert [(level.price, level.size) for level in book.bids] == [
        (Decimal("72141.5"), Decimal("2.5"))
    ]
    assert [(level.price, level.size) for level in book.asks] == [
        (Decimal("72142.0"), Decimal("3.0"))
    ]
    assert book.event_time == utc_from_micros(1700000000005000)


def test_order_book_l2_normalizes_levels() -> None:
    message = OrderBookL2Event(
        type="ob_l2",
        a=[[Decimal("16919.0"), Decimal("1087")], [Decimal("16919.5"), Decimal("1193")]],
        b=[[Decimal("16918.0"), Decimal("602")]],
        sy="BTCUSD",
        ts=1700000000000000,
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    book = cast(OrderBookEvent, result.events[0])
    assert book.kind == "l2"
    assert book.is_snapshot is True
    assert [level.price for level in book.asks] == [
        Decimal("16919.0"),
        Decimal("16919.5"),
    ]
    assert [(level.price, level.size) for level in book.bids] == [
        (Decimal("16918.0"), Decimal("602"))
    ]


def test_order_book_updates_snapshot_keeps_sequence() -> None:
    message = OrderBookUpdatesEvent(
        type="ob_updates",
        action="snapshot",
        seq=6199,
        cs=2178756498,
        a=[[Decimal("16919.0"), Decimal("1087")]],
        b=[[Decimal("16918.0"), Decimal("602")]],
        sy="BTCUSD",
        ts=1700000000000000,
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    book = cast(OrderBookEvent, result.events[0])
    assert book.kind == "full"
    assert book.is_snapshot is True
    assert book.sequence == 6199


def test_order_book_updates_update_is_not_snapshot() -> None:
    message = OrderBookUpdatesEvent(
        type="ob_updates",
        action="update",
        seq=6200,
        a=[[Decimal("16919.0"), Decimal("0")]],
        b=[],
        sy="BTCUSD",
        ts=1700000000000000,
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "normalized"
    book = cast(OrderBookEvent, result.events[0])
    assert book.is_snapshot is False
    assert book.sequence == 6200


def test_heartbeat_is_ignored() -> None:
    result = DeltaNormalizer().normalize(HeartbeatEvent(type="heartbeat"))
    assert result.status == "ignored"
    assert result.events == ()


def test_system_status_is_ignored() -> None:
    result = DeltaNormalizer().normalize(
        SystemStatusEvent(type="system_status", status="maintenance")
    )
    assert result.status == "ignored"
    assert result.events == ()


def test_unsupported_market_price_message() -> None:
    message = MarkPriceEvent(
        type="mark_price", p=Decimal("72124.5"), sy="MARK:BTCUSD", ts=1700000000000000
    )
    result = DeltaNormalizer().normalize(message)
    assert result.status == "unsupported"
    assert result.events == ()


def test_unknown_message_is_unsupported() -> None:
    result = DeltaNormalizer().normalize(
        UnknownWSEvent(type="brand_new_channel", payload={})
    )
    assert result.status == "unsupported"
    assert result.events == ()
