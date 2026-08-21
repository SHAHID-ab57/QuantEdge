"""Tests for the candle repository.

Exercises all SQL in ``CandleRepository`` against an in-memory SQLite
database with the full schema (unique keys and check constraints enforced).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Candle, Exchange, Market
from app.repositories.candles import CandleRepository

SessionFactory = async_sessionmaker[AsyncSession]

BASE = datetime(2026, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def utc(hour: int) -> datetime:
    return BASE + timedelta(hours=hour)


def naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()



@pytest_asyncio.fixture
async def market_id(session_factory: SessionFactory) -> uuid.UUID:
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol="ETHUSD",
            base_asset="ETH",
            quote_asset="USD",
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()
        return market.id


async def seed(
    session_factory: SessionFactory,
    market_id: uuid.UUID,
    open_times: list[datetime],
    timeframe: str = "1h",
    source: str = "delta",
) -> None:
    async with session_factory() as session:
        for open_time in open_times:
            session.add(
                Candle(
                    market_id=market_id,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + HOUR,
                    open=Decimal("3050.50"),
                    high=Decimal("3060.00"),
                    low=Decimal("3040.00"),
                    close=Decimal("3055.25"),
                    volume=Decimal("120.5"),
                    quote_volume=None,
                    trade_count=None,
                    source=source,
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_get_candles_ascending_and_paginated(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2), utc(3), utc(4)])

    async with session_factory() as session:
        repo = CandleRepository(session)
        page = await repo.get_candles(market_id, "1h", limit=2, offset=1)

    assert [naive(c.open_time) for c in page] == [naive(utc(1)), naive(utc(2))]


@pytest.mark.asyncio
async def test_get_candles_range_filter_is_half_open(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2), utc(3)])

    async with session_factory() as session:
        repo = CandleRepository(session)
        page = await repo.get_candles(
            market_id, "1h", start=utc(1), end=utc(3), limit=100, offset=0
        )

    assert [naive(c.open_time) for c in page] == [naive(utc(1)), naive(utc(2))]


@pytest.mark.asyncio
async def test_count_candles_respects_range(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2), utc(3)])

    async with session_factory() as session:
        repo = CandleRepository(session)
        total = await repo.count_candles(market_id, "1h", start=utc(1), end=utc(4))

    assert total == 3


@pytest.mark.asyncio
async def test_get_candles_scoped_to_timeframe(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1)], timeframe="1h")
    await seed(session_factory, market_id, [utc(0)], timeframe="1d")

    async with session_factory() as session:
        repo = CandleRepository(session)
        page = await repo.get_candles(market_id, "1d", limit=100, offset=0)

    assert len(page) == 1


@pytest.mark.asyncio
async def test_get_latest_candle(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2)])

    async with session_factory() as session:
        repo = CandleRepository(session)
        latest = await repo.get_latest_candle(market_id, "1h")
        none_latest = await repo.get_latest_candle(market_id, "1d")

    assert latest is not None
    assert naive(latest.open_time) == naive(utc(2))
    assert none_latest is None


@pytest.mark.asyncio
async def test_candle_exists(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0)])

    async with session_factory() as session:
        repo = CandleRepository(session)
        assert await repo.candle_exists(market_id, "1h") is True
        assert await repo.candle_exists(market_id, "1d") is False
        assert await repo.candle_exists(market_id, "1h", open_time=utc(0)) is True
        assert await repo.candle_exists(market_id, "1h", open_time=utc(1)) is False


@pytest.mark.asyncio
async def test_get_available_timeframes(
    engine: AsyncEngine, session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0)], timeframe="1h")
    await seed(session_factory, market_id, [utc(0)], timeframe="5m")
    await seed(session_factory, market_id, [utc(0)], timeframe="1d")

    async with session_factory() as session:
        repo = CandleRepository(session)
        timeframes = await repo.get_available_timeframes(market_id)

    assert timeframes == ["1d", "1h", "5m"]