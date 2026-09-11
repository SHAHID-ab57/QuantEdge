"""Tests for `OrderFlowCapture` — the order-flow persistence layer.

A real bus event in, a real stored row out. The capture is a mechanism
only: these tests confirm it persists what flows past it and nothing more.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import app.services.order_flow_capture as order_flow_capture_module
from app.events import EventBus
from app.marketdata.bus_events import OrderBookUpdated, TradeEventReceived
from app.marketdata.models import OrderBookEvent, OrderBookLevel, TradeEvent
from app.marketdata.orderbook import OrderBookAggregator
from app.models.order_flow import OrderBookSnapshotRow, TradeFlowRow
from app.repositories.order_flow import OrderFlowRepository
from app.services.order_flow_capture import OrderFlowCapture
from tests.conftest import SessionFactory

pytestmark = pytest.mark.asyncio


def _trade(symbol: str = "ETHUSD", price: str = "2500.5", size: str = "1.25") -> TradeEventReceived:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    return TradeEventReceived(
        source="test",
        trade=TradeEvent(
            exchange="delta",
            symbol=symbol,
            event_time=now,
            trade_time=now,
            side="buy",
            price=Decimal(price),
            size=Decimal(size),
        ),
    )


def _book(symbol: str = "ETHUSD", *, seq: int = 7) -> OrderBookUpdated:
    return OrderBookUpdated(
        source="test",
        order_book=OrderBookEvent(
            exchange="delta",
            symbol=symbol,
            event_time=datetime(2026, 9, 11, 12, 0, 5, tzinfo=UTC),
            sequence=seq,
            kind="full",
            bids=[OrderBookLevel(price=Decimal("2499"), size=Decimal("3"))],
            asks=[OrderBookLevel(price=Decimal("2501"), size=Decimal("4"))],
            is_snapshot=True,
        ),
    )


@pytest.fixture(autouse=True)
def _engine_patch(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(order_flow_capture_module, "get_engine", lambda: engine)


async def test_start_noops_without_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(order_flow_capture_module, "get_engine", lambda: None)
    capture = OrderFlowCapture(aggregator=OrderBookAggregator(), symbols=("ETHUSD",))
    await capture.start()
    assert capture.running is False
    await capture.stop()


async def test_buffers_a_bus_trade_and_flushes_it_to_the_database(
    engine: AsyncEngine, session_factory: SessionFactory
) -> None:
    bus = EventBus()
    capture = OrderFlowCapture(aggregator=OrderBookAggregator(), symbols=("ETHUSD",)).attach(bus)

    await bus.publish(_trade(price="2500.5", size="1.25"))
    await bus.drain()
    await capture._flush_trades()

    async with session_factory() as session:
        repo = OrderFlowRepository(session)
        assert await repo.count_trades("ETHUSD") == 1
    assert capture.trades_captured == 1


async def test_buffer_max_forces_an_early_flush(
    engine: AsyncEngine, session_factory: SessionFactory
) -> None:
    capture = OrderFlowCapture(
        aggregator=OrderBookAggregator(), symbols=("ETHUSD",), trade_buffer_max=3
    )
    for _ in range(3):
        await capture._on_trade(_trade())

    async with session_factory() as session:
        assert await OrderFlowRepository(session).count_trades() == 3


async def test_snapshots_the_reconstructed_book_not_a_raw_message(
    engine: AsyncEngine, session_factory: SessionFactory
) -> None:
    aggregator = OrderBookAggregator()
    bus = EventBus()
    aggregator.attach(bus)
    await bus.publish(_book(seq=42))
    await bus.drain()

    capture = OrderFlowCapture(aggregator=aggregator, symbols=("ETHUSD",), snapshot_depth=5)
    await capture._capture_snapshots()

    async with session_factory() as session:
        row = await OrderFlowRepository(session).latest_snapshot("ETHUSD")
    assert row is not None
    assert row.sequence == 42
    assert row.depth == 5
    assert row.bids == [["2499", "3"]]
    assert row.asks == [["2501", "4"]]
    assert capture.snapshots_captured == 1


async def test_capture_ignores_symbols_with_no_reconstructed_book(
    engine: AsyncEngine, session_factory: SessionFactory
) -> None:
    capture = OrderFlowCapture(aggregator=OrderBookAggregator(), symbols=("ETHUSD",))
    await capture._capture_snapshots()

    async with session_factory() as session:
        assert await OrderFlowRepository(session).count_snapshots() == 0


async def test_a_persistence_failure_is_swallowed_and_does_not_lose_the_loop(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = OrderFlowCapture(aggregator=OrderBookAggregator(), symbols=("ETHUSD",))
    await capture._on_trade(_trade())

    async def boom(*_a: object, **_k: object) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(OrderFlowRepository, "add_trades", boom)
    await capture._flush_trades()  # must not raise
    assert capture.trades_captured == 0


async def test_prune_deletes_rows_past_the_retention_window_and_keeps_recent_ones(
    engine: AsyncEngine, session_factory: SessionFactory
) -> None:
    # Real wall-clock times, not a simulated `now` — `_prune` computes its own
    # cutoff from `datetime.now(UTC)`, so the fixture data is anchored to
    # that same clock rather than faking it.
    now = datetime.now(UTC)
    old = now - timedelta(days=61)
    async with session_factory() as session:
        session.add_all(
            [
                TradeFlowRow(
                    exchange="delta",
                    symbol="ETHUSD",
                    event_time=old,
                    side="buy",
                    price=Decimal("2500"),
                    size=Decimal("1"),
                    captured_at=old,
                ),
                TradeFlowRow(
                    exchange="delta",
                    symbol="ETHUSD",
                    event_time=now,
                    side="buy",
                    price=Decimal("2500"),
                    size=Decimal("1"),
                    captured_at=now,
                ),
                OrderBookSnapshotRow(
                    exchange="delta",
                    symbol="ETHUSD",
                    event_time=old,
                    depth=5,
                    bids=[["2499", "3"]],
                    asks=[["2501", "4"]],
                    captured_at=old,
                ),
                OrderBookSnapshotRow(
                    exchange="delta",
                    symbol="ETHUSD",
                    event_time=now,
                    depth=5,
                    bids=[["2499", "3"]],
                    asks=[["2501", "4"]],
                    captured_at=now,
                ),
            ]
        )
        await session.commit()

    capture = OrderFlowCapture(
        aggregator=OrderBookAggregator(), symbols=("ETHUSD",), retention_days=60
    )
    await capture._prune()

    async with session_factory() as session:
        repo = OrderFlowRepository(session)
        assert await repo.count_trades("ETHUSD") == 1
        assert await repo.count_snapshots("ETHUSD") == 1
    assert capture.trades_pruned == 1
    assert capture.snapshots_pruned == 1


async def test_a_prune_failure_is_swallowed_and_does_not_lose_the_loop(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = OrderFlowCapture(aggregator=OrderBookAggregator(), symbols=("ETHUSD",))

    async def boom(*_a: object, **_k: object) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(OrderFlowRepository, "prune_trades_older_than", boom)
    await capture._prune()  # must not raise
    assert capture.trades_pruned == 0
