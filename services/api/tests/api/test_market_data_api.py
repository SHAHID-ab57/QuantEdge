"""API tests for the market data endpoints.

Runs the full FastAPI stack against an in-memory SQLite database via a
dependency override for the database session.
"""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
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
from app.models import Candle, Exchange, Market

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


@pytest.fixture
def client(session_factory: SessionFactory) -> Generator[TestClient]:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded(session_factory: SessionFactory) -> None:
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


def test_list_markets(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["markets"][0]["symbol"] == "ETHUSD"
    assert body["markets"][0]["market_type"] == "perpetual"
    assert body["markets"][0]["exchange"] == "Delta Exchange"


@pytest_asyncio.fixture
async def seeded_with_metadata(session_factory: SessionFactory) -> None:
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


def test_list_markets_includes_product_metadata(
    client: TestClient, seeded_with_metadata: None
) -> None:
    response = client.get("/api/v1/markets")

    assert response.status_code == 200
    market = response.json()["markets"][0]
    assert market["exchange_id"] == market["id"] or market["exchange_id"] is not None
    assert market["delta_product_id"] == 27
    assert market["delta_contract_type"] == "perpetual_futures"
    assert market["tick_size"] == "0.5"
    assert market["funding_method"] == "mark_price"
    assert market["funding_interval_seconds"] == 28800
    assert market["listing_date"] == "2023-12-18T13:10:39Z"


def test_list_timeframes(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/ETHUSD/timeframes")

    assert response.status_code == 200
    assert response.json() == {"symbol": "ETHUSD", "timeframes": ["1h"]}


def test_list_timeframes_unknown_symbol(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/NOPE/timeframes")

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


def test_get_candles_ascending_with_pagination(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "limit": 2, "offset": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["open_time"] for item in body["items"]] == [
        "2026-01-01T01:00:00Z",
        "2026-01-01T02:00:00Z",
    ]
    assert body["pagination"] == {
        "total": 5,
        "returned": 2,
        "has_more": True,
        "limit": 2,
        "offset": 1,
    }
    assert body["items"][0]["open"] == "3050.5"
    assert body["items"][0]["quote_volume"] is None


def test_get_candles_range_filter(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T01:00:00Z",
            "end": "2026-01-01T04:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["has_more"] is False


def test_get_candles_unknown_symbol(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/NOPE/candles", params={"timeframe": "1h"})

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


def test_get_candles_invalid_timeframe(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/ETHUSD/candles", params={"timeframe": "7d"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_timeframe"


def test_get_candles_reversed_range(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T04:00:00Z",
            "end": "2026-01-01T01:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


def test_get_candles_one_sided_range(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={"timeframe": "1h", "start": "2026-01-01T01:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


def test_get_candles_negative_limit_rejected(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "limit": -1}
    )

    assert response.status_code == 422


def test_get_candles_limit_over_max_rejected(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "limit": 1001}
    )

    assert response.status_code == 422


def test_get_candles_negative_offset_rejected(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "offset": -1}
    )

    assert response.status_code == 422


def test_get_latest(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/ETHUSD/latest", params={"timeframe": "1h"})

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["candle"]["open_time"] == "2026-01-01T04:00:00Z"


def test_get_latest_no_candles(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/ETHUSD/latest", params={"timeframe": "1d"})

    assert response.status_code == 404
    assert response.json()["code"] == "candle_not_found"


def test_get_latest_unknown_symbol(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/NOPE/latest", params={"timeframe": "1h"})

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


def test_get_candle_stats(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={"timeframe": "1h"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["timeframe"] == "1h"
    assert body["start"] is None
    assert body["end"] is None
    assert body["total_candles"] == 5
    assert body["highest_price"] == "3060"
    assert body["lowest_price"] == "3040"
    assert body["average_volume"] == "120.5"
    assert body["first_candle"]["open_time"] == "2026-01-01T00:00:00Z"
    assert body["last_candle"]["open_time"] == "2026-01-01T04:00:00Z"
    assert body["first_candle"]["close"] == "3055.25"


def test_get_candle_stats_range(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T03:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_candles"] == 3
    assert body["start"] == "2026-01-01T00:00:00Z"
    assert body["end"] == "2026-01-01T03:00:00Z"
    assert body["first_candle"]["open_time"] == "2026-01-01T00:00:00Z"
    assert body["last_candle"]["open_time"] == "2026-01-01T02:00:00Z"


def test_get_candle_stats_no_candles(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1d",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "candle_not_found"


def test_get_candle_stats_empty_range(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1h",
            "start": "2026-01-02T00:00:00Z",
            "end": "2026-01-03T00:00:00Z",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "candle_not_found"


def test_get_candle_stats_invalid_timeframe(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={"timeframe": "7d"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_timeframe"


def test_get_candle_stats_invalid_range(client: TestClient, seeded: None) -> None:
    response = client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1h",
            "start": "2026-01-02T00:00:00Z",
            "end": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


def test_get_research_reports_coverage(client: TestClient, seeded: None) -> None:
    """Research metrics match the stored 1h range with no gaps."""
    response = client.get("/api/v1/markets/ETHUSD/research")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["total_candles"] == 5
    assert body["oldest_candle_at"] == "2026-01-01T00:00:00Z"
    assert body["newest_candle_at"] == "2026-01-01T04:00:00Z"
    assert body["coverage_days"] == 0.2
    assert len(body["timeframes"]) == 1
    entry = body["timeframes"][0]
    assert entry["timeframe"] == "1h"
    assert entry["stored_candles"] == 5
    assert entry["oldest_at"] == "2026-01-01T00:00:00Z"
    assert entry["newest_at"] == "2026-01-01T04:00:00Z"
    assert entry["expected_candles"] == 5
    assert entry["missing_candles"] == 0
    assert entry["completeness"] == 100.0
    assert entry["average_daily_candles"] == 25.0


@pytest_asyncio.fixture
async def seeded_with_gap(session_factory: SessionFactory) -> None:
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


def test_get_research_counts_gaps(client: TestClient, seeded_with_gap: None) -> None:
    """Missing buckets inside the stored range are reported per timeframe."""
    response = client.get("/api/v1/markets/BTCUSD/research")

    assert response.status_code == 200
    entry = response.json()["timeframes"][0]
    assert entry["stored_candles"] == 5
    assert entry["expected_candles"] == 6
    assert entry["missing_candles"] == 1
    assert entry["completeness"] == round(100.0 * 5 / 6, 1)
    assert entry["coverage_days"] == 0.2


def test_get_research_unknown_symbol(client: TestClient, seeded: None) -> None:
    response = client.get("/api/v1/markets/NOPE/research")

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


def test_openapi_documents_endpoints_and_errors(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/markets" in paths
    assert "/api/v1/markets/{symbol}/timeframes" in paths
    assert "/api/v1/markets/{symbol}/research" in paths
    assert "/api/v1/markets/{symbol}/candles" in paths
    assert "/api/v1/markets/{symbol}/candles/stats" in paths
    assert "/api/v1/markets/{symbol}/latest" in paths

    candles = paths["/api/v1/markets/{symbol}/candles"]["get"]
    param_names = [param["name"] for param in candles["parameters"]]
    assert "timeframe" in param_names
    assert "start" in param_names
    assert "end" in param_names
    assert "limit" in param_names
    assert "offset" in param_names
    assert "400" in candles["responses"]
    assert "404" in candles["responses"]
    assert candles["responses"]["400"]["content"]["application/json"]["examples"][
        "invalid_timeframe"
    ]