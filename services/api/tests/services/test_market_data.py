"""Tests for the market data service.

Validates business rules (symbol/timeframe/range/limit), DTO mapping, and
domain error raising against in-memory SQLite.
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
from app.repositories.markets import MarketRepository
from app.services.market_data import (
    CandleNotFoundError,
    InvalidRangeError,
    InvalidTimeframeError,
    LimitExceededError,
    MarketDataService,
    MarketNotFoundError,
)

SessionFactory = async_sessionmaker[AsyncSession]

BASE = datetime(2026, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def utc(hour: int) -> datetime:
    return BASE + timedelta(hours=hour)


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
async def session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(bind=engine, expire_on_commit=False)


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
                    source="delta",
                )
            )
        await session.commit()


def service(session_factory: SessionFactory) -> MarketDataService:
    return MarketDataService(
        candle_repository=CandleRepository(session_factory()),
        market_repository=MarketRepository(session_factory()),
        default_limit=100,
        max_limit=1000,
    )


@pytest.mark.asyncio
async def test_list_markets_returns_dtos(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    response = await service(session_factory).list_markets()

    assert response.total == 1
    assert response.markets[0].symbol == "ETHUSD"
    assert response.markets[0].market_type == "perpetual"
    assert response.markets[0].is_active is True


@pytest.mark.asyncio
async def test_get_timeframes_distinct_with_data(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0)], timeframe="1h")
    await seed(session_factory, market_id, [utc(0)], timeframe="1d")

    response = await service(session_factory).get_timeframes("ETHUSD")

    assert response.symbol == "ETHUSD"
    assert response.timeframes == ["1d", "1h"]


@pytest.mark.asyncio
async def test_get_timeframes_empty_when_no_data(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    response = await service(session_factory).get_timeframes("ETHUSD")

    assert response.timeframes == []


@pytest.mark.asyncio
async def test_get_candles_pagination_metadata(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2), utc(3), utc(4)])

    response = await service(session_factory).get_candles(
        "ETHUSD", "1h", limit=2, offset=2
    )

    assert [item.open_time for item in response.items] == [utc(2), utc(3)]
    assert response.pagination.total == 5
    assert response.pagination.returned == 2
    assert response.pagination.has_more is True
    assert response.items[0].volume == Decimal("120.5")


@pytest.mark.asyncio
async def test_get_candles_last_page_has_no_more(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2)])

    response = await service(session_factory).get_candles(
        "ETHUSD", "1h", limit=2, offset=2
    )

    assert response.pagination.returned == 1
    assert response.pagination.has_more is False


@pytest.mark.asyncio
async def test_get_candles_naive_range_treated_as_utc(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1), utc(2)])

    response = await service(session_factory).get_candles(
        "ETHUSD",
        "1h",
        start=datetime(2026, 1, 1, 1, 0),
        end=datetime(2026, 1, 1, 3, 0),
        limit=100,
        offset=0,
    )

    assert [item.open_time for item in response.items] == [utc(1), utc(2)]


@pytest.mark.asyncio
async def test_unknown_symbol_raises(session_factory: SessionFactory) -> None:
    with pytest.raises(MarketNotFoundError) as exc_info:
        await service(session_factory).get_candles("NOPE", "1h", limit=10, offset=0)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "market_not_found"


@pytest.mark.asyncio
async def test_invalid_timeframe_raises(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    with pytest.raises(InvalidTimeframeError) as exc_info:
        await service(session_factory).get_candles("ETHUSD", "7d", limit=10, offset=0)
    assert exc_info.value.code == "invalid_timeframe"


@pytest.mark.asyncio
async def test_one_sided_range_raises(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    with pytest.raises(InvalidRangeError, match="together"):
        await service(session_factory).get_candles(
            "ETHUSD", "1h", start=utc(0), limit=10, offset=0
        )


@pytest.mark.asyncio
async def test_reversed_range_raises(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    with pytest.raises(InvalidRangeError, match="after start"):
        await service(session_factory).get_candles(
            "ETHUSD", "1h", start=utc(2), end=utc(1), limit=10, offset=0
        )


@pytest.mark.asyncio
async def test_limit_over_max_raises(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    with pytest.raises(LimitExceededError) as exc_info:
        await service(session_factory).get_candles("ETHUSD", "1h", limit=1001, offset=0)
    assert exc_info.value.code == "limit_exceeded"


@pytest.mark.asyncio
async def test_latest_candle(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    await seed(session_factory, market_id, [utc(0), utc(1)])

    response = await service(session_factory).get_latest_candle("ETHUSD", "1h")

    assert response.candle.open_time == utc(1)


@pytest.mark.asyncio
async def test_latest_candle_missing_raises(
    session_factory: SessionFactory, market_id: uuid.UUID
) -> None:
    with pytest.raises(CandleNotFoundError) as exc_info:
        await service(session_factory).get_latest_candle("ETHUSD", "1h")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "candle_not_found"