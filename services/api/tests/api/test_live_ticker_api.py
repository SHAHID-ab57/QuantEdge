"""API tests for GET /markets/{symbol}/ticker (live ticker + funding)."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.dependencies.live_market import get_live_market_service
from app.schemas.market_data import LiveTickerResponse

pytestmark = pytest.mark.asyncio


class _StubLiveMarketService:
    def __init__(self, response: LiveTickerResponse) -> None:
        self._response = response
        self.symbols: list[str] = []

    async def get_ticker(self, symbol: str) -> LiveTickerResponse:
        self.symbols.append(symbol)
        return self._response


async def test_ticker_endpoint_serializes_live_snapshot(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    stub = _StubLiveMarketService(
        LiveTickerResponse(
            symbol="ETHUSD",
            as_of=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            source="ws",
            last_price=Decimal("2465.7"),
            bid=Decimal("2465.65"),
            ask=Decimal("2465.70"),
            mark_price=Decimal("2465.66"),
            open_interest=Decimal("17934.2"),
            funding_rate=Decimal("-0.001156"),
            funding_interval_seconds=28800,
            next_funding_time=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
        )
    )
    app.dependency_overrides[get_live_market_service] = lambda: stub

    response = await client.get("/api/v1/markets/ethusd/ticker")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["source"] == "ws"
    assert body["last_price"] == "2465.7"
    assert body["open_interest"] == "17934.2"
    assert body["funding_rate"] == "-0.001156"
    assert body["funding_interval_seconds"] == 28800
    assert body["next_funding_time"] == "2026-09-11T16:00:00Z"
    assert body["as_of"] == "2026-09-11T12:00:00Z"


async def test_ticker_endpoint_all_null_when_no_live_data(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    stub = _StubLiveMarketService(LiveTickerResponse(symbol="ETHUSD"))
    app.dependency_overrides[get_live_market_service] = lambda: stub

    response = await client.get("/api/v1/markets/ETHUSD/ticker")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "none"
    assert body["last_price"] is None
    assert body["funding_rate"] is None
    assert body["as_of"] is None
