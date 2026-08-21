"""Tests for the market repository."""

import uuid
from collections.abc import AsyncGenerator

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
from app.models import Exchange, Market
from app.repositories.markets import MarketRepository

SessionFactory = async_sessionmaker[AsyncSession]


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
async def exchange_id(session_factory: SessionFactory) -> uuid.UUID:
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.commit()
        return exchange.id


async def seed_market(
    session_factory: SessionFactory,
    exchange_id: uuid.UUID,
    symbol: str,
) -> uuid.UUID:
    async with session_factory() as session:
        market = Market(
            exchange_id=exchange_id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="spot",
        )
        session.add(market)
        await session.commit()
        return market.id


@pytest.mark.asyncio
async def test_get_all_orders_by_symbol(
    engine: AsyncEngine, session_factory: SessionFactory, exchange_id: uuid.UUID
) -> None:
    await seed_market(session_factory, exchange_id, "BTCUSD")
    await seed_market(session_factory, exchange_id, "ETHUSD")
    await seed_market(session_factory, exchange_id, "ADAUSD")

    async with session_factory() as session:
        markets = await MarketRepository(session).get_all()

    assert [m.symbol for m in markets] == ["ADAUSD", "BTCUSD", "ETHUSD"]


@pytest.mark.asyncio
async def test_get_by_symbol(
    engine: AsyncEngine, session_factory: SessionFactory, exchange_id: uuid.UUID
) -> None:
    market_id = await seed_market(session_factory, exchange_id, "ETHUSD")

    async with session_factory() as session:
        repo = MarketRepository(session)
        found = await repo.get_by_symbol("ETHUSD")
        missing = await repo.get_by_symbol("NOPE")

    assert found is not None
    assert found.id == market_id
    assert missing is None