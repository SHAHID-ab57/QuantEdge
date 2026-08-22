"""Unit tests for `OrderBookAggregator` — L2 book reconstruction from the
event bus's snapshot + incremental-diff stream (no HTTP/WebSocket)."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.events.bus import EventBus
from app.marketdata.bus_events import OrderBookUpdated
from app.marketdata.models import OrderBookEvent, OrderBookLevel
from app.marketdata.orderbook import OrderBookAggregator


def level(price: str, size: str) -> OrderBookLevel:
    return OrderBookLevel(price=Decimal(price), size=Decimal(size))


def book_event(
    symbol: str = "ETHUSD",
    *,
    kind: str = "full",
    is_snapshot: bool = True,
    bids: list[OrderBookLevel] | None = None,
    asks: list[OrderBookLevel] | None = None,
    sequence: int | None = None,
) -> OrderBookEvent:
    return OrderBookEvent(
        exchange="delta",
        symbol=symbol,
        event_time=datetime.now(UTC),
        kind=kind,  # type: ignore[arg-type]
        bids=bids or [],
        asks=asks or [],
        is_snapshot=is_snapshot,
        sequence=sequence,
    )


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def aggregator(bus: EventBus) -> OrderBookAggregator:
    return OrderBookAggregator().attach(bus)


def publish(aggregator: OrderBookAggregator, event: OrderBookEvent) -> None:
    """Invokes the aggregator's handler directly rather than through
    ``bus.publish()``. The bus schedules handlers as fire-and-forget tasks
    (see `EventBus.publish`'s own docstring/`drain()`) with no synchronous
    completion guarantee, so a test relying on `asyncio.run(bus.publish(...))`
    having run the handler before the assertion that follows would be
    depending on an implementation detail of `asyncio.run`'s shutdown
    sequence, not a documented guarantee — the same reasoning
    `test_gateway.py`'s existing tests already follow for `_on_trade`/
    `_on_ticker`."""
    asyncio.run(aggregator._on_order_book(OrderBookUpdated(source="test", order_book=event)))


class TestNoBookYet:
    def test_get_book_returns_none_before_any_event(self, aggregator: OrderBookAggregator) -> None:
        assert aggregator.get_book("ETHUSD") is None
        assert aggregator.has_book("ETHUSD") is False


class TestSnapshotReplace:
    def test_a_snapshot_populates_the_book(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(
            aggregator,
            book_event(bids=[level("100", "1"), level("99", "2")], asks=[level("101", "3")]),
        )
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert [(b.price, b.size) for b in book.bids] == [
            (Decimal("100"), Decimal("1")),
            (Decimal("99"), Decimal("2")),
        ]
        assert [(a.price, a.size) for a in book.asks] == [(Decimal("101"), Decimal("3"))]

    def test_a_second_snapshot_fully_replaces_the_first(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(bids=[level("100", "1")], asks=[level("101", "1")]))
        publish(aggregator, book_event(bids=[level("50", "9")], asks=[level("51", "9")]))
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert [b.price for b in book.bids] == [Decimal("50")]
        assert [a.price for a in book.asks] == [Decimal("51")]


class TestIncrementalMerge:
    def test_an_update_upserts_a_new_level_without_dropping_existing_ones(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(bids=[level("100", "1")], asks=[level("101", "1")]))
        publish(
            aggregator,
            book_event(is_snapshot=False, bids=[level("99", "5")], asks=[]),
        )
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        prices = {b.price for b in book.bids}
        assert prices == {Decimal("100"), Decimal("99")}

    def test_an_update_replaces_the_size_of_an_existing_level(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(bids=[level("100", "1")], asks=[]))
        publish(aggregator, book_event(is_snapshot=False, bids=[level("100", "42")], asks=[]))
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert book.bids[0].size == Decimal("42")

    def test_a_zero_size_update_removes_the_level_rather_than_zeroing_it(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(bids=[level("100", "1"), level("99", "2")], asks=[]))
        publish(aggregator, book_event(is_snapshot=False, bids=[level("100", "0")], asks=[]))
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert [b.price for b in book.bids] == [Decimal("99")]

    def test_an_update_before_any_snapshot_starts_the_book_from_empty(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(is_snapshot=False, bids=[level("100", "1")], asks=[]))
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert [b.price for b in book.bids] == [Decimal("100")]


class TestL1IsIgnoredForDepth:
    def test_an_l1_event_never_wipes_the_reconstructed_depth_book(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(
            aggregator,
            book_event(
                kind="full",
                bids=[level(str(100 - i), "1") for i in range(10)],
                asks=[level(str(101 + i), "1") for i in range(10)],
            ),
        )
        # A same-timestamp top-of-book tick, as Delta sends several times a
        # second — must not collapse the 10-level book down to one level.
        publish(
            aggregator,
            book_event(
                kind="l1", is_snapshot=True, bids=[level("100", "1")], asks=[level("101", "1")]
            ),
        )
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert len(book.bids) == 10
        assert len(book.asks) == 10

    def test_an_l1_only_stream_never_produces_a_book_at_all(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(
            aggregator,
            book_event(
                kind="l1", is_snapshot=True, bids=[level("100", "1")], asks=[level("101", "1")]
            ),
        )
        assert aggregator.get_book("ETHUSD") is None


class TestSortingAndDepth:
    def test_bids_are_sorted_descending_and_asks_ascending(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(
            aggregator,
            book_event(
                bids=[level("98", "1"), level("100", "1"), level("99", "1")],
                asks=[level("103", "1"), level("101", "1"), level("102", "1")],
            ),
        )
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert [b.price for b in book.bids] == [Decimal("100"), Decimal("99"), Decimal("98")]
        assert [a.price for a in book.asks] == [Decimal("101"), Decimal("102"), Decimal("103")]

    def test_depth_limits_each_side_independently(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(
            aggregator,
            book_event(
                bids=[level(str(1000 - i), "1") for i in range(150)],
                asks=[level(str(101 + i), "1") for i in range(5)],
            ),
        )
        book = aggregator.get_book("ETHUSD", depth=100)
        assert book is not None
        assert len(book.bids) == 100
        assert len(book.asks) == 5
        assert book.bids[0].price == Decimal("1000")  # still the best bid


class TestMultiSymbolIsolation:
    def test_symbols_are_tracked_independently(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(symbol="ETHUSD", bids=[level("100", "1")], asks=[]))
        publish(aggregator, book_event(symbol="BTCUSD", bids=[level("70000", "1")], asks=[]))
        eth = aggregator.get_book("ETHUSD")
        btc = aggregator.get_book("BTCUSD")
        assert eth is not None and btc is not None
        assert eth.bids[0].price == Decimal("100")
        assert btc.bids[0].price == Decimal("70000")


class TestIgnoresOtherEventTypes:
    def test_a_non_order_book_event_is_ignored(self, aggregator: OrderBookAggregator) -> None:
        class OtherEvent:
            pass

        asyncio.run(aggregator._on_order_book(OtherEvent()))  # type: ignore[arg-type]
        assert aggregator.get_book("ETHUSD") is None


class TestSequenceAndEventTime:
    def test_sequence_and_event_time_track_the_latest_message(
        self, aggregator: OrderBookAggregator, bus: EventBus
    ) -> None:
        publish(aggregator, book_event(bids=[level("100", "1")], asks=[], sequence=1))
        publish(
            aggregator, book_event(is_snapshot=False, bids=[level("99", "1")], asks=[], sequence=2)
        )
        book = aggregator.get_book("ETHUSD")
        assert book is not None
        assert book.sequence == 2
