"""Shared test fixtures, environment isolation, and opt-in test flags.

The root conftest owns everything shared across the test suite:

- Environment isolation (no database/network by default).
- Opt-in flags (``--run-integration``, ``--run-performance``) with matching
  collection-time skips.
- The in-memory SQLite engine + session factory used by most tests.
- The async HTTP ``client`` fixture (httpx over ASGI with lifespan).
- Reusable seeded data fixtures (exchange, market, candles).
- Sample market-data domain objects and an ``EventBus`` fixture.
- An opt-in PostgreSQL profile (``postgres`` marker) that runs against
  ``TEST_DATABASE_URL`` and auto-skips when the database is unreachable.
"""

import os
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

os.environ["DATABASE_URL"] = ""
os.environ["DB_URL"] = ""

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.application import create_app
from app.db.base import Base
from app.db.session import get_db
from app.events.bus import EventBus
from app.marketdata.models import OrderBookEvent, OrderBookLevel, TickerEvent, TradeEvent
from app.models import Candle, Exchange, Market

SessionFactory = async_sessionmaker[AsyncSession]

BASE = datetime(2026, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def utc(hour: int) -> datetime:
    """Hour offset from the fixed 2026-01-01 test base time."""
    return BASE + timedelta(hours=hour)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the opt-in flags that enable slow or external test groups."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that call real external APIs",
    )
    parser.addoption(
        "--run-performance",
        action="store_true",
        default=False,
        help="Run performance tests with timing budgets",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip opt-in test groups unless their flag is passed."""
    run_integration = config.getoption("--run-integration")
    run_performance = config.getoption("--run-performance")
    for item in items:
        if "integration" in item.keywords and not run_integration:
            item.add_marker(
                pytest.mark.skip(reason="integration tests require --run-integration")
            )
        if "performance" in item.keywords and not run_performance:
            item.add_marker(
                pytest.mark.skip(reason="performance tests require --run-performance")
            )


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """In-memory SQLite engine with the full schema applied."""
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
    """Session factory bound to the shared test engine."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """An open session for the duration of a test."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def app(session_factory: SessionFactory) -> Generator[FastAPI]:
    """A fresh FastAPI app whose database dependency uses the test engine."""
    app = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client exercising the app through the ASGI interface."""
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as test_client:
            yield test_client


@pytest_asyncio.fixture
async def seeded(session_factory: SessionFactory) -> None:
    """One exchange with an ETHUSD perpetual market and five 1h candles."""
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
        market_id = market.id
        for hour in range(5):
            open_time = utc(hour)
            session.add(
                Candle(
                    market_id=market_id,
                    timeframe="1h",
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


@pytest_asyncio.fixture
async def seeded_with_metadata(session_factory: SessionFactory) -> None:
    """A BTCUSD market carrying full Delta product metadata."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        session.add(
            Market(
                exchange_id=exchange.id,
                symbol="BTCUSD",
                base_asset="BTC",
                quote_asset="USD",
                market_type="perpetual",
                delta_product_id=27,
                delta_contract_type="perpetual_futures",
                tick_size="0.5",
                funding_method="mark_price",
                funding_interval_seconds=28800,
                listing_date=datetime(2023, 12, 18, 13, 10, 39, tzinfo=UTC),
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def seeded_with_gap(session_factory: SessionFactory) -> None:
    """A BTCUSD market whose candles skip the 03:00 bucket."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol="BTCUSD",
            base_asset="BTC",
            quote_asset="USD",
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()
        for hour in (0, 1, 2, 4, 5):  # 03:00 bucket missing
            open_time = utc(hour)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + HOUR,
                    open=Decimal("60000"),
                    high=Decimal("60100"),
                    low=Decimal("59900"),
                    close=Decimal("60050"),
                    volume=Decimal("1"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


@pytest_asyncio.fixture
async def seeded_varied(session_factory: SessionFactory) -> None:
    """Three 1h candles with distinct OHLCV values for sort tests."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol="ETCUSD",
            base_asset="ETC",
            quote_asset="USD",
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()
        rows = [
            (Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("100")),
            (Decimal("20"), Decimal("25"), Decimal("19"), Decimal("24"), Decimal("200")),
            (Decimal("30"), Decimal("33"), Decimal("28"), Decimal("32"), Decimal("300")),
        ]
        for hour, (open_price, high, low, close, volume) in enumerate(rows):
            open_time = utc(hour)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + HOUR,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


@pytest_asyncio.fixture
async def seeded_with_issues(session_factory: SessionFactory) -> None:
    """Candles with an invalid-OHLC row and an overlapping out-of-order row."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol="SOLUSD",
            base_asset="SOL",
            quote_asset="USD",
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()

        def add_candle(open_time: datetime, *, high: Decimal) -> None:
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + HOUR,
                    open=Decimal("100"),
                    high=high,
                    low=Decimal("90"),
                    close=Decimal("98"),
                    volume=Decimal("10"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )

        add_candle(utc(0), high=Decimal("110"))
        add_candle(utc(1), high=Decimal("105"))
        await session.execute(text("PRAGMA ignore_check_constraints = ON"))
        add_candle(utc(2), high=Decimal("95"))  # high < open/close: invalid OHLC
        add_candle(utc(2) + timedelta(minutes=30), high=Decimal("106"))  # overlap
        await session.commit()


@pytest.fixture
def trade_event() -> TradeEvent:
    """A canonical buy trade on ETHUSD."""
    return TradeEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=utc(0),
        side="buy",
        price=Decimal("3050.5"),
        size=Decimal("1.25"),
    )


@pytest.fixture
def ticker_event() -> TickerEvent:
    """A canonical ticker update for ETHUSD."""
    return TickerEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=utc(0),
        bid=Decimal("3050.0"),
        ask=Decimal("3051.0"),
        last_price=Decimal("3050.5"),
        mark_price=Decimal("3050.75"),
    )


@pytest.fixture
def order_book_event() -> OrderBookEvent:
    """A canonical L2 order book snapshot for ETHUSD."""
    return OrderBookEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=utc(0),
        kind="l2",
        bids=[OrderBookLevel(price=Decimal("3050"), size=Decimal("10"))],
        asks=[OrderBookLevel(price=Decimal("3051"), size=Decimal("8"))],
        is_snapshot=True,
    )


@pytest.fixture
def event_bus() -> EventBus:
    """A fresh event bus with no subscribers."""
    return EventBus()


@pytest_asyncio.fixture
async def postgres_engine() -> AsyncGenerator[AsyncEngine]:
    """Opt-in PostgreSQL engine from ``TEST_DATABASE_URL``.

    Used only by tests marked ``postgres``. The fixture creates the schema
    in an isolated ``test_<session-pid>`` schema and auto-skips the test
    when the database is unreachable.
    """
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://research:research@localhost:5432/eth_platform_test",
    )
    engine = create_async_engine(url, future=True)
    schema = f"test_{os.getpid()}"
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL test database unreachable at {url}: {exc}")
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(
    postgres_engine: AsyncEngine,
) -> SessionFactory:
    """Session factory bound to the isolated PostgreSQL schema."""
    return async_sessionmaker(bind=postgres_engine, expire_on_commit=False)