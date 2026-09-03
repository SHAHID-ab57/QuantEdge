"""Tests for the Delta market synchronization service.

Database-backed tests run against an in-memory SQLite database so the whole
sync pipeline (fetch -> validate -> upsert) is exercised without external
dependencies.
"""

import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.integrations.delta.client import DeltaClient
from app.integrations.delta.config import DeltaConfig
from app.models import Exchange, Market
from app.services.market_sync import MarketSyncError, sync_markets

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
SessionFactory = async_sessionmaker[AsyncSession]

BASE_URL = "https://api.india.delta.exchange"


def client_for(handler: Handler) -> DeltaClient:
    """Build a Delta client over a mocked transport."""
    transport = httpx.MockTransport(handler)
    return DeltaClient(
        DeltaConfig(base_url=BASE_URL, api_key="", api_secret="", request_timeout=5.0),
        transport=transport,
    )


def make_product(
    symbol: str,
    contract_type: str,
    *,
    base: str = "BTC",
    quote: str = "USD",
    product_id: int,
) -> dict[str, object]:
    """Build a Delta ``/v2/products`` payload entry."""
    return {
        "id": product_id,
        "symbol": symbol,
        "contract_type": contract_type,
        "state": "live",
        "underlying_asset": {"symbol": base},
        "quoting_asset": {"symbol": quote},
        "tick_size": "0.5",
        "launch_time": "2023-12-18T13:10:39Z",
        "funding_method": "mark_price",
        "product_specs": {"rate_exchange_interval": 28800},
    }


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """In-memory SQLite engine with the market data schema applied."""
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
    """Session factory bound to the test engine."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def handler_for(
    products: list[dict[str, object]],
    captured: dict[str, object] | None = None,
) -> Handler:
    """Return a mock handler returning the given product list."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["url"] = str(request.url)
        return httpx.Response(200, json={"success": True, "result": products})

    return handler


async def count_markets(session: AsyncSession, exchange_id: uuid.UUID | None = None) -> int:
    """Count market rows, optionally scoped to an exchange."""
    statement = select(func.count()).select_from(Market)
    if exchange_id is not None:
        statement = statement.where(Market.exchange_id == exchange_id)
    return (await session.execute(statement)).scalar_one()


@pytest.mark.asyncio
async def test_sync_inserts_markets_and_creates_exchange(
    session_factory: SessionFactory,
) -> None:
    """A fresh catalog creates the exchange record and inserts every market."""
    products = [
        make_product("BTCUSD", "perpetual_futures", product_id=1),
        make_product("ETHUSD", "spot", base="ETH", product_id=2),
        make_product("SOLUSDT", "futures", base="SOL", quote="USDT", product_id=3),
    ]
    client = client_for(handler_for(products))

    report = await sync_markets(client=client, session=session_factory())

    assert report.products_fetched == 3
    assert report.inserted == 3
    assert report.updated == 0
    assert report.skipped == 0
    assert isinstance(report.exchange_id, uuid.UUID)

    async with session_factory() as session:
        exchange = await session.get(Exchange, report.exchange_id)
        assert exchange is not None
        assert exchange.slug == "delta"
        assert exchange.name == "Delta Exchange"

        markets = {
            market.symbol: market for market in (await session.execute(select(Market))).scalars()
        }
    assert markets["BTCUSD"].market_type == "perpetual"
    assert markets["ETHUSD"].market_type == "spot"
    assert markets["SOLUSDT"].market_type == "expiry"
    assert markets["SOLUSDT"].base_asset == "SOL"
    assert markets["SOLUSDT"].quote_asset == "USDT"


@pytest.mark.asyncio
async def test_sync_persists_product_metadata(session_factory: SessionFactory) -> None:
    """Upstream product metadata is stored with the market on insert."""
    products = [make_product("BTCUSD", "perpetual_futures", product_id=27)]
    client = client_for(handler_for(products))

    await sync_markets(client=client, session=session_factory())

    async with session_factory() as check:
        market = (await check.execute(select(Market))).scalar_one()
    assert market.delta_product_id == 27
    assert market.delta_contract_type == "perpetual_futures"
    assert market.tick_size == "0.5"
    assert market.funding_method == "mark_price"
    assert market.funding_interval_seconds == 28800
    assert market.listing_date is not None
    assert market.listing_date.year == 2023


@pytest.mark.asyncio
async def test_sync_updates_changed_metadata(session_factory: SessionFactory) -> None:
    """A changed upstream metadata value updates the stored market."""
    original = [make_product("BTCUSD", "perpetual_futures", product_id=27)]
    changed = [
        {
            **make_product("BTCUSD", "perpetual_futures", product_id=27),
            "tick_size": "1",
            "product_specs": {"rate_exchange_interval": 14400},
        }
    ]

    first = await sync_markets(client=client_for(handler_for(original)), session=session_factory())
    assert first.inserted == 1

    second = await sync_markets(client=client_for(handler_for(changed)), session=session_factory())
    assert second.updated == 1
    assert second.skipped == 0

    async with session_factory() as check:
        market = (await check.execute(select(Market))).scalar_one()
        assert market.tick_size == "1"
        assert market.funding_interval_seconds == 14400


@pytest.mark.asyncio
async def test_sync_is_idempotent(session_factory: SessionFactory) -> None:
    """Re-syncing an unchanged catalog skips every market instead of duplicating."""
    products = [make_product("BTCUSD", "perpetual_futures", product_id=1)]
    client = client_for(handler_for(products))
    session = session_factory()

    first = await sync_markets(client=client, session=session)
    second = await sync_markets(client=client, session=session)

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped == 1
    assert second.updated == 0

    async with session_factory() as check:
        assert await count_markets(check) == 1


@pytest.mark.asyncio
async def test_sync_updates_changed_market(session_factory: SessionFactory) -> None:
    """A changed quote asset on a later sync updates the stored market."""
    original = [make_product("BTCUSD", "perpetual_futures", quote="USDT", product_id=1)]
    changed = [make_product("BTCUSD", "perpetual_futures", quote="USD", product_id=1)]

    first = await sync_markets(client=client_for(handler_for(original)), session=session_factory())
    assert first.inserted == 1

    second = await sync_markets(client=client_for(handler_for(changed)), session=session_factory())
    assert second.updated == 1
    assert second.inserted == 0
    assert second.skipped == 0

    async with session_factory() as check:
        market = (await check.execute(select(Market))).scalar_one()
        assert market.quote_asset == "USD"


@pytest.mark.asyncio
async def test_sync_skips_unsupported_contract_type(
    session_factory: SessionFactory,
) -> None:
    """Products with an unknown contract type are skipped, not inserted."""
    products = [
        make_product("BTCUSD", "perpetual_futures", product_id=1),
        make_product("BTC-OPT", "options", product_id=2),
    ]
    client = client_for(handler_for(products))

    report = await sync_markets(client=client, session=session_factory())

    assert report.inserted == 1
    assert report.skipped == 1

    async with session_factory() as check:
        assert await count_markets(check) == 1


@pytest.mark.asyncio
async def test_sync_skips_duplicate_symbols(session_factory: SessionFactory) -> None:
    """Duplicate symbols in one payload insert once and skip the repeats."""
    products = [
        make_product("BTCUSD", "perpetual_futures", product_id=1),
        make_product("BTCUSD", "perpetual_futures", product_id=2),
    ]
    client = client_for(handler_for(products))

    report = await sync_markets(client=client, session=session_factory())

    assert report.inserted == 1
    assert report.skipped == 1

    async with session_factory() as check:
        assert await count_markets(check) == 1


@pytest.mark.asyncio
async def test_sync_raises_on_truncated_catalog(
    session_factory: SessionFactory,
) -> None:
    """A catalog at the page-size boundary aborts the sync without writing."""
    products = [
        make_product(f"COIN{i}USD", "spot", base=f"COIN{i}", product_id=i) for i in range(500)
    ]
    client = client_for(handler_for(products))

    with pytest.raises(MarketSyncError):
        await sync_markets(client=client, session=session_factory())

    async with session_factory() as check:
        exchange_count = (
            await check.execute(select(func.count()).select_from(Exchange))
        ).scalar_one()
        assert exchange_count == 0
        assert await count_markets(check) == 0


@pytest.mark.asyncio
async def test_sync_fetches_products_with_expected_filters(
    session_factory: SessionFactory,
) -> None:
    """The products endpoint is called with the configured filters and path."""
    captured: dict[str, object] = {}
    client = client_for(handler_for([], captured))

    await sync_markets(client=client, session=session_factory())

    url = str(captured["url"])
    assert "/v2/products" in url
    assert "states=live" in url
    assert "contract_types=perpetual_futures%2Cspot%2Cfutures" in url
    assert "page_size=500" in url
