"""Real Delta Exchange India API integration test (opt-in only).

This test calls the live public candles endpoint and writes into the
configured database. It never runs during the normal suite: it is marked
``integration`` and requires ``--run-integration``.

Run with:

    uv run pytest tests/manual/test_real_candle_ingest.py -m integration \\
        --run-integration -v

Environment configuration (all optional):

    DELTA_INTEGRATION_SYMBOL    default ETHUSDT
    DELTA_INTEGRATION_TIMEFRAME default 1h
    DELTA_INTEGRATION_DAYS      default 3
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import build_engine
from app.integrations.delta import get_delta_client
from app.models import Candle, Exchange, Market
from app.services.candle_ingest import ingest_candles

# Delta India's catalog has no ETHUSDT product; ETHUSD is the ETH market.
SYMBOL = os.environ.get("DELTA_INTEGRATION_SYMBOL", "ETHUSD")
TIMEFRAME = os.environ.get("DELTA_INTEGRATION_TIMEFRAME", "1h")
DAYS = int(os.environ.get("DELTA_INTEGRATION_DAYS", "3"))

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_delta_ingest_is_idempotent() -> None:
    """Ingest a recent range from the live API twice; the second run must
    insert nothing."""
    for variable in ("DATABASE_URL", "DB_URL"):
        os.environ.pop(variable, None)
    get_settings.cache_clear()

    if not get_settings().database_url:
        pytest.fail("DATABASE_URL is not configured; cannot run integration test")

    engine = build_engine()
    session = async_sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _ensure_market(session, SYMBOL)

        end = datetime.now(UTC)
        start = end - timedelta(days=DAYS)

        client = get_delta_client()
        stored_before = await _count_stored(engine, SYMBOL)
        try:
            first = await ingest_candles(
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                start=start,
                end=end,
                client=client,
                session=session,
            )
            second = await ingest_candles(
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                start=start,
                end=end,
                client=client,
                session=session,
            )
        finally:
            await client.aclose()

        assert first.received > 0, (
            "expected records from the live API for "
            f"{SYMBOL}/{TIMEFRAME} — verify the symbol exists on Delta India "
            "(use DELTA_INTEGRATION_SYMBOL to override)"
        )
        assert second.inserted == 0, "second run must be fully idempotent"
        assert (
            second.duplicates_skipped
            == first.duplicates_skipped + first.inserted
        ), "second run must skip everything the first run accepted"

        stored_after = await _count_stored(engine, SYMBOL)
        assert stored_after == stored_before + first.inserted + second.inserted
    finally:
        await session.close()
        await engine.dispose()


async def _ensure_market(session: AsyncSession, symbol: str) -> None:
    """Create the Delta exchange and market rows when they are missing."""
    async with session.begin():
        exchange = (
            await session.execute(select(Exchange).where(Exchange.slug == "delta"))
        ).scalar_one_or_none()
        if exchange is None:
            exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
            session.add(exchange)
            await session.flush()
        market = (
            await session.execute(
                select(Market).where(
                    Market.exchange_id == exchange.id, Market.symbol == symbol
                )
            )
        ).scalar_one_or_none()
        if market is None:
            session.add(
                Market(
                    exchange_id=exchange.id,
                    symbol=symbol,
                    base_asset=symbol.removesuffix("USDT"),
                    quote_asset="USDT",
                    market_type="spot",
                )
            )


async def _count_stored(engine: AsyncEngine, symbol: str) -> int:
    """Count candles stored for the given symbol (separate connection)."""
    async with engine.connect() as conn:
        count = await conn.execute(
            select(func.count())
            .select_from(Candle)
            .join(Market, Candle.market_id == Market.id)
            .where(Market.symbol == symbol)
        )
        return count.scalar_one()