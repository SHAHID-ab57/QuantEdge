"""Opt-in integration test for the market data API against the real database.

Requires ``--run-integration`` and a configured ``DATABASE_URL``.
"""

import os

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.application import create_app
from app.core.config import get_settings

pytestmark = pytest.mark.integration

SYMBOL = os.environ.get("DELTA_INTEGRATION_SYMBOL", "ETHUSD")
TIMEFRAME = os.environ.get("DELTA_INTEGRATION_TIMEFRAME", "1h")


async def test_real_market_data_api() -> None:
    for variable in ("DATABASE_URL", "DB_URL"):
        os.environ.pop(variable, None)
    get_settings.cache_clear()
    if not get_settings().database_url:
        pytest.fail("DATABASE_URL is not configured; cannot run integration test")

    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            markets = await client.get("/api/v1/markets")
            assert markets.status_code == 200
            symbols = [market["symbol"] for market in markets.json()["markets"]]
            assert SYMBOL in symbols

            timeframes = await client.get(f"/api/v1/markets/{SYMBOL}/timeframes")
            assert timeframes.status_code == 200
            assert TIMEFRAME in timeframes.json()["timeframes"]

            page = await client.get(
                f"/api/v1/markets/{SYMBOL}/candles",
                params={"timeframe": TIMEFRAME, "limit": 10},
            )
            assert page.status_code == 200
            body = page.json()
            assert body["pagination"]["returned"] == min(10, body["pagination"]["total"])
            assert body["pagination"]["total"] > 0
            items = body["items"]
            assert items == sorted(items, key=lambda candle: candle["open_time"])

            offset = 10
            newest = items[-1]
            while body["pagination"]["has_more"]:
                body = (
                    await client.get(
                        f"/api/v1/markets/{SYMBOL}/candles",
                        params={"timeframe": TIMEFRAME, "limit": 10, "offset": offset},
                    )
                ).json()
                items = body["items"]
                assert items == sorted(items, key=lambda candle: candle["open_time"])
                newest = items[-1]
                offset += 10

            latest = await client.get(
                f"/api/v1/markets/{SYMBOL}/latest", params={"timeframe": TIMEFRAME}
            )
            assert latest.status_code == 200
            assert latest.json()["candle"]["open_time"] == newest["open_time"]
