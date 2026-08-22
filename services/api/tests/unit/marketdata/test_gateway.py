"""Unit tests for the live market-stream gateway (no HTTP/WebSocket)."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.events.bus import EventBus
from app.marketdata.bus_events import TickerUpdated, TradeEventReceived
from app.marketdata.gateway import MarketStreamGateway, _ticker_payload, _trade_payload
from app.marketdata.models import TickerEvent, TradeEvent
from app.state.manager import MarketStateManager


def make_trade(symbol: str = "ETHUSD", price: str = "1900") -> TradeEvent:
    return TradeEvent(
        exchange="delta",
        symbol=symbol,
        event_time=datetime.now(UTC),
        side="unknown",
        price=Decimal(price),
        size=Decimal("1"),
    )


def make_ticker(symbol: str = "ETHUSD") -> TickerEvent:
    return TickerEvent(
        exchange="delta",
        symbol=symbol,
        event_time=datetime.now(UTC),
        last_price=Decimal("1901"),
        price_change_24h=Decimal("12.5"),
    )


@pytest.fixture
def state_manager() -> MarketStateManager:
    return MarketStateManager()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def gateway(state_manager: MarketStateManager, bus: EventBus) -> MarketStreamGateway:
    return MarketStreamGateway(state_manager).attach(bus)


class TestRegistration:
    def test_register_and_unregister_track_connection_count(
        self, gateway: MarketStreamGateway
    ) -> None:
        handle = gateway.register()
        assert gateway.connection_count() == 1
        gateway.unregister(handle)
        assert gateway.connection_count() == 0
        assert gateway.metrics.connections_opened == 1
        assert gateway.metrics.connections_closed == 1

    def test_unregister_clears_its_subscriptions(self, gateway: MarketStreamGateway) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        assert gateway.subscriber_count("ETHUSD") == 1
        gateway.unregister(handle)
        assert gateway.subscriber_count("ETHUSD") == 0


class TestSubscribe:
    def test_subscribe_normalizes_symbol_case_and_whitespace(
        self, gateway: MarketStreamGateway
    ) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, [" ethusd "])
        assert gateway.subscriber_count("ETHUSD") == 1
        assert handle.symbols == {"ETHUSD"}

    def test_subscribe_ignores_blank_symbols(self, gateway: MarketStreamGateway) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["  ", ""])
        assert handle.symbols == set()

    def test_subscribe_queues_an_empty_snapshot_for_an_unknown_symbol(
        self, gateway: MarketStreamGateway
    ) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        message = handle.queue.get_nowait()
        assert message == {"type": "snapshot", "symbol": "ETHUSD", "trade": None, "ticker": None}

    def test_subscribe_queues_a_populated_snapshot_when_state_exists(
        self,
        gateway: MarketStreamGateway,
        state_manager: MarketStateManager,
        bus: EventBus,
    ) -> None:
        state_manager.attach(bus)
        asyncio.run(bus.publish(TradeEventReceived(source="test", trade=make_trade(price="1950"))))
        asyncio.run(bus.drain())

        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        message = handle.queue.get_nowait()
        assert message["type"] == "snapshot"
        assert message["trade"] == {
            "price": "1950",
            "size": "1",
            "side": "unknown",
            "event_time": message["trade"]["event_time"],
        }
        assert message["ticker"] is None

    def test_unsubscribe_stops_further_delivery(self, gateway: MarketStreamGateway) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        handle.queue.get_nowait()  # drain the snapshot
        gateway.unsubscribe(handle, ["ETHUSD"])

        asyncio.run(
            asyncio.wait_for(
                gateway._on_trade(TradeEventReceived(source="test", trade=make_trade())), 1
            )
        )
        assert handle.queue.empty()


class TestFanout:
    def test_trade_event_reaches_every_subscriber_of_that_symbol_only(
        self, gateway: MarketStreamGateway
    ) -> None:
        subscribed = gateway.register()
        other_symbol = gateway.register()
        gateway.subscribe(subscribed, ["ETHUSD"])
        gateway.subscribe(other_symbol, ["BTCUSD"])
        subscribed.queue.get_nowait()  # drain snapshots
        other_symbol.queue.get_nowait()

        asyncio.run(gateway._on_trade(TradeEventReceived(source="test", trade=make_trade())))

        message = subscribed.queue.get_nowait()
        assert message["type"] == "trade"
        assert message["symbol"] == "ETHUSD"
        assert message["data"]["price"] == "1900"
        assert other_symbol.queue.empty()

    def test_ticker_event_reaches_subscribers(self, gateway: MarketStreamGateway) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        handle.queue.get_nowait()

        asyncio.run(gateway._on_ticker(TickerUpdated(source="test", ticker=make_ticker())))

        message = handle.queue.get_nowait()
        assert message["type"] == "ticker"
        assert message["data"]["last_price"] == "1901"
        assert message["data"]["price_change_24h"] == "12.5"

    def test_unrelated_bus_events_are_ignored(self, gateway: MarketStreamGateway) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        handle.queue.get_nowait()

        class OtherEvent:
            pass

        asyncio.run(gateway._on_trade(OtherEvent()))  # type: ignore[arg-type]
        assert handle.queue.empty()

    def test_a_full_queue_drops_the_message_and_counts_it(
        self, state_manager: MarketStateManager, bus: EventBus
    ) -> None:
        gateway = MarketStreamGateway(state_manager).attach(bus)
        handle = gateway.register()
        # Fill the (small, test-only) queue beyond capacity.
        handle.queue = asyncio.Queue(maxsize=1)
        gateway.subscribe(handle, ["ETHUSD"])  # 1st message: the snapshot fills the queue

        asyncio.run(gateway._on_trade(TradeEventReceived(source="test", trade=make_trade())))

        assert gateway.metrics.messages_dropped == 1


class TestMetrics:
    def test_snapshot_reports_all_counters(self, gateway: MarketStreamGateway) -> None:
        snapshot = gateway.metrics.snapshot()
        assert set(snapshot) == {
            "connections_opened",
            "connections_closed",
            "messages_sent",
            "messages_dropped",
        }


class TestWireTimestampFormat:
    """Regression coverage for a bug where every trade/ticker/snapshot frame
    was silently dropped by the frontend: ``datetime.isoformat()`` renders a
    UTC-aware datetime with a ``+00:00`` offset, but the frontend's Zod
    ``z.string().datetime()`` schemas accept only a literal ``Z`` suffix by
    default. Heartbeat pongs carry no timestamp, so the connection looked
    healthy (open, latency measured) while carrying zero market data. See
    ``_isoformat_utc`` and the matching convention in
    ``app/schemas/market_data.py``.
    """

    def test_trade_payload_event_time_uses_a_z_suffix(self) -> None:
        trade = make_trade()
        payload = _trade_payload(trade)
        assert payload["event_time"].endswith("Z")  # type: ignore[union-attr]
        assert "+00:00" not in payload["event_time"]  # type: ignore[operator]

    def test_ticker_payload_event_time_uses_a_z_suffix(self) -> None:
        ticker = make_ticker()
        payload = _ticker_payload(ticker)
        assert payload["event_time"].endswith("Z")  # type: ignore[union-attr]
        assert "+00:00" not in payload["event_time"]  # type: ignore[operator]

    def test_a_naive_datetime_is_treated_as_utc(self) -> None:
        naive = make_trade()
        naive.event_time = naive.event_time.replace(tzinfo=None)
        payload = _trade_payload(naive)
        assert payload["event_time"].endswith("Z")  # type: ignore[union-attr]

    def test_a_non_utc_timezone_is_converted_before_formatting(self) -> None:
        from datetime import timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        shifted = make_trade()
        shifted.event_time = shifted.event_time.astimezone(ist)
        payload = _trade_payload(shifted)
        assert payload["event_time"].endswith("Z")  # type: ignore[union-attr]
        assert "+05:30" not in payload["event_time"]  # type: ignore[operator]
