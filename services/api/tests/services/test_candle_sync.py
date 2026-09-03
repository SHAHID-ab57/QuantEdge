"""Tests for the periodic candle catch-up synchronization service.

The scheduler's database reads run against an in-memory SQLite engine;
ingestion itself is faked so these tests focus on window computation,
pair resolution, skipping, and failure isolation (the real ingestion path
is covered by :mod:`tests.services.test_candle_ingest`).
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.models import Candle, Exchange, Market
from app.services import candle_sync
from app.services.candle_ingest import IngestReport
from app.services.candle_sync import CandleSyncScheduler, _truncate_to_bucket

FIXED_NOW = datetime(2026, 8, 20, 16, 33, 35, tzinfo=UTC)


class FakeDatetime(datetime):
    """datetime with a frozen ``now()`` for deterministic window tests."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return FIXED_NOW


def fake_ingest(
    *,
    report: IngestReport | None = None,
    failure_symbol: str | None = None,
) -> tuple[Callable[..., Any], list[tuple[str, str, datetime, datetime]]]:
    """Build an ``ingest_candles`` fake that records calls."""
    calls: list[tuple[str, str, datetime, datetime]] = []

    async def ingest(
        *, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> IngestReport:
        calls.append((symbol, timeframe, start, end))
        if failure_symbol is not None and symbol == failure_symbol:
            raise RuntimeError("boom")
        return report or IngestReport(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            api_requests=1,
            received=1,
            accepted=1,
            rejected=0,
            inserted=1,
            duplicates_skipped=0,
            duration_seconds=0.01,
        )

    return ingest, calls


async def seed_market(
    session_factory: async_sessionmaker[AsyncSession],
    symbol: str = "ETHUSD",
    *,
    active: bool = True,
) -> uuid.UUID:
    """Create the Delta exchange and one market; return the market id."""
    async with session_factory() as session:
        exchange = (
            await session.execute(select(Exchange).where(Exchange.slug == "delta"))
        ).scalar_one_or_none()
        if exchange is None:
            exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
            session.add(exchange)
            await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset="ETH",
            quote_asset="USD",
            market_type="perpetual",
            is_active=active,
        )
        session.add(market)
        await session.commit()
        return market.id


async def seed_candle(
    session_factory: async_sessionmaker[AsyncSession],
    market_id: uuid.UUID,
    *,
    timeframe: str = "1h",
    open_time: datetime | None = None,
) -> None:
    """Insert one candle for the market."""
    open_time = open_time or FIXED_NOW - timedelta(hours=5)
    duration = timedelta(hours=1) if timeframe.endswith("h") else timedelta(minutes=1)
    async with session_factory() as session:
        session.add(
            Candle(
                market_id=market_id,
                timeframe=timeframe,
                open_time=open_time,
                close_time=open_time + duration,
                open="3050.50",
                high="3060.00",
                low="3040.00",
                close="3055.25",
                volume="120.5",
                source="delta",
            )
        )
        await session.commit()


def test_truncate_to_bucket() -> None:
    """Bucket flooring respects the resolution grid."""
    now = FIXED_NOW
    assert _truncate_to_bucket(now, timedelta(hours=1)) == datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    assert _truncate_to_bucket(now, timedelta(minutes=1)) == datetime(
        2026, 8, 20, 16, 33, tzinfo=UTC
    )
    assert _truncate_to_bucket(now, timedelta(hours=4)) == datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    assert _truncate_to_bucket(now, timedelta(days=1)) == datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_start_noops_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a database the scheduler does not create a loop task."""
    monkeypatch.setattr(candle_sync, "get_engine", lambda: None)
    scheduler = CandleSyncScheduler(symbols=["ETHUSD"])
    await scheduler.start()
    assert not scheduler.running
    await scheduler.stop()


@pytest.mark.asyncio
async def test_window_backfills_when_nothing_stored(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty markets seed from the backfill window, ending at the closed bucket."""
    await seed_market(session_factory, "ETHUSD")
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD"], timeframes=["1h"], backfill_days=7)
    window = await scheduler._catch_up_window("ETHUSD", "1h")
    assert window is not None
    start, end = window
    assert end == datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    assert start == datetime(2026, 8, 13, 16, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_window_resumes_after_last_candle(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored candles resume one bucket after the newest open time."""
    market_id = await seed_market(session_factory, "ETHUSD")
    await seed_candle(
        session_factory,
        market_id,
        open_time=datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD"], timeframes=["1h"])
    window = await scheduler._catch_up_window("ETHUSD", "1h")
    assert window is not None
    start, end = window
    assert start == datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 8, 20, 16, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_window_is_none_when_current(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A market whose newest bucket is current is skipped."""
    market_id = await seed_market(session_factory, "ETHUSD")
    await seed_candle(
        session_factory,
        market_id,
        open_time=datetime(2026, 8, 20, 15, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD"], timeframes=["1h"])
    assert await scheduler._catch_up_window("ETHUSD", "1h") is None


@pytest.mark.asyncio
async def test_run_catch_up_syncs_all_pairs(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every symbol/timeframe pair is ingested with its computed window."""
    await seed_market(session_factory, "ETHUSD")
    await seed_market(session_factory, "BTCUSD")
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(candle_sync, "ingest_candles", ingest)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD", "BTCUSD"], timeframes=["1h", "4h"])
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 4
    assert summary.synced == 4
    assert summary.failed == 0
    symbols = {call[0] for call in calls}
    timeframes = {call[1] for call in calls}
    assert symbols == {"ETHUSD", "BTCUSD"}
    assert timeframes == {"1h", "4h"}
    for _, _, start, end in calls:
        assert start < end
        assert end == datetime(2026, 8, 20, 16, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_run_catch_up_skips_inactive_and_unknown_markets(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inactive markets and symbols missing from the database are excluded."""
    await seed_market(session_factory, "ETHUSD", active=False)
    await seed_market(session_factory, "BTCUSD")
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(candle_sync, "ingest_candles", ingest)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD", "BTCUSD", "NOPEUSD"], timeframes=["1h"])
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 1
    assert [call[0] for call in calls] == ["BTCUSD"]


@pytest.mark.asyncio
async def test_run_catch_up_isolates_failures(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failing pair does not stop the remaining pairs."""
    await seed_market(session_factory, "ETHUSD")
    await seed_market(session_factory, "BTCUSD")
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest(failure_symbol="ETHUSD")
    monkeypatch.setattr(candle_sync, "ingest_candles", ingest)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD", "BTCUSD"], timeframes=["1h"])
    summary = await scheduler.run_catch_up()

    assert summary.failed == 1
    assert summary.synced == 1
    assert [call[0] for call in calls] == ["BTCUSD", "ETHUSD"]


@pytest.mark.asyncio
async def test_run_catch_up_skips_current_pairs(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pairs already current are counted as skipped and not ingested."""
    market_id = await seed_market(session_factory, "ETHUSD")
    await seed_candle(
        session_factory,
        market_id,
        open_time=datetime(2026, 8, 20, 15, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(candle_sync, "ingest_candles", ingest)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD"], timeframes=["1h"])
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 1
    assert summary.skipped == 1
    assert calls == []


@pytest.mark.asyncio
async def test_loop_runs_ticks_until_stopped(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background loop starts, runs a tick, and stops cleanly."""
    await seed_market(session_factory, "ETHUSD")
    monkeypatch.setattr(candle_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(candle_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(candle_sync, "ingest_candles", ingest)

    scheduler = CandleSyncScheduler(symbols=["ETHUSD"], timeframes=["1h"], interval_seconds=60)
    await scheduler.start()
    assert scheduler.running

    for _ in range(50):
        if calls:
            break
        await asyncio.sleep(0.02)
    assert calls, "first tick never ran"

    await scheduler.stop()
    assert not scheduler.running
    assert [call[1] for call in calls] == ["1h"]
