"""Unit tests for the live market-stream gateway (no HTTP/WebSocket)."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.events.bus import EventBus
from app.marketdata.bus_events import OrderBookUpdated, TickerUpdated, TradeEventReceived
from app.marketdata.gateway import MarketStreamGateway, _ticker_payload, _trade_payload
from app.marketdata.models import OrderBookEvent, OrderBookLevel, TickerEvent, TradeEvent
from app.marketdata.orderbook import OrderBookAggregator
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
def order_book(bus: EventBus) -> OrderBookAggregator:
    return OrderBookAggregator().attach(bus)


@pytest.fixture
def gateway(
    state_manager: MarketStateManager, order_book: OrderBookAggregator, bus: EventBus
) -> MarketStreamGateway:
    return MarketStreamGateway(state_manager, order_book).attach(bus)


def make_book_event(
    symbol: str = "ETHUSD",
    *,
    kind: str = "full",
    is_snapshot: bool = True,
    bids: list[OrderBookLevel] | None = None,
    asks: list[OrderBookLevel] | None = None,
) -> OrderBookEvent:
    return OrderBookEvent(
        exchange="delta",
        symbol=symbol,
        event_time=datetime.now(UTC),
        kind=kind,  # type: ignore[arg-type]
        bids=bids or [],
        asks=asks or [],
        is_snapshot=is_snapshot,
    )


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
        assert message == {
            "type": "snapshot",
            "symbol": "ETHUSD",
            "trade": None,
            "ticker": None,
            "orderbook": None,
        }

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


class TestOrderBookRelay:
    """The gateway relays the *aggregator's reconstructed* book, not the raw
    bus event — see `orderbook.py` for why a raw incremental diff can't be
    shown to a browser client on its own."""

    def test_subscribe_snapshot_includes_no_book_before_any_order_book_event(
        self, gateway: MarketStreamGateway
    ) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        message = handle.queue.get_nowait()
        assert message["orderbook"] is None

    def test_subscribe_snapshot_includes_the_reconstructed_book(
        self, gateway: MarketStreamGateway, order_book: OrderBookAggregator
    ) -> None:
        # Feeds the aggregator directly (bypassing the bus's fire-and-forget
        # scheduling — see `test_orderbook.py`'s `publish()` docstring for why).
        asyncio.run(
            order_book._on_order_book(
                OrderBookUpdated(
                    source="test",
                    order_book=make_book_event(
                        bids=[OrderBookLevel(price=Decimal("100"), size=Decimal("1"))],
                        asks=[OrderBookLevel(price=Decimal("101"), size=Decimal("2"))],
                    ),
                )
            )
        )
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        message = handle.queue.get_nowait()
        assert message["orderbook"]["bids"] == [{"price": "100", "size": "1"}]
        assert message["orderbook"]["asks"] == [{"price": "101", "size": "2"}]

    def test_an_order_book_update_is_fanned_out_as_the_reconstructed_book(
        self, gateway: MarketStreamGateway, order_book: OrderBookAggregator
    ) -> None:
        handle = gateway.register()
        gateway.subscribe(handle, ["ETHUSD"])
        handle.queue.get_nowait()  # drain the initial (empty) snapshot

        # In production both the aggregator and the gateway are independently
        # subscribed to the same bus event; driving both handlers in order
        # reproduces that without depending on the bus's async scheduling.
        event = OrderBookUpdated(
            source="test",
            order_book=make_book_event(
                bids=[OrderBookLevel(price=Decimal("100"), size=Decimal("1"))],
                asks=[],
            ),
        )
        asyncio.run(order_book._on_order_book(event))
        asyncio.run(gateway._on_order_book(event))
        message = handle.queue.get_nowait()
        assert message["type"] == "orderbook"
        assert message["symbol"] == "ETHUSD"
        assert message["data"]["bids"] == [{"price": "100", "size": "1"}]

    def test_only_subscribers_of_the_affected_symbol_receive_the_update(
        self, gateway: MarketStreamGateway, order_book: OrderBookAggregator
    ) -> None:
        eth_handle = gateway.register()
        gateway.subscribe(eth_handle, ["ETHUSD"])
        eth_handle.queue.get_nowait()
        btc_handle = gateway.register()
        gateway.subscribe(btc_handle, ["BTCUSD"])
        btc_handle.queue.get_nowait()

        event = OrderBookUpdated(
            source="test",
            order_book=make_book_event(
                symbol="ETHUSD",
                bids=[OrderBookLevel(price=Decimal("100"), size=Decimal("1"))],
                asks=[],
            ),
        )
        asyncio.run(order_book._on_order_book(event))
        asyncio.run(gateway._on_order_book(event))
        assert eth_handle.queue.qsize() == 1
        assert btc_handle.queue.empty()

    def test_a_gateway_without_an_order_book_aggregator_reports_no_book(
        self, state_manager: MarketStateManager, bus: EventBus
    ) -> None:
        # Matches the constructor's optional `order_book` parameter — a
        # gateway can still be built without one (e.g. in an older test),
        # and must degrade to "no book" rather than raising.
        bare_gateway = MarketStreamGateway(state_manager).attach(bus)
        handle = bare_gateway.register()
        bare_gateway.subscribe(handle, ["ETHUSD"])
        message = handle.queue.get_nowait()
        assert message["orderbook"] is None

        asyncio.run(
            bare_gateway._on_order_book(
                OrderBookUpdated(
                    source="test",
                    order_book=make_book_event(
                        bids=[OrderBookLevel(price=Decimal("100"), size=Decimal("1"))], asks=[]
                    ),
                )
            )
        )
        assert handle.queue.empty()
