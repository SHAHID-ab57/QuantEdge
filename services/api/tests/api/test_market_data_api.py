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


def test_openapi_documents_endpoints_and_errors(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/markets" in paths
    assert "/api/v1/markets/{symbol}/timeframes" in paths
    assert "/api/v1/markets/{symbol}/candles" in paths
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