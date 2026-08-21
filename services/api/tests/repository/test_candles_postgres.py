"""PostgreSQL-backed repository tests (opt-in profile).

Marked ``postgres``: the fixture reads ``TEST_DATABASE_URL`` (defaulting
to ``postgresql+asyncpg://research:research@localhost:5432/eth_platform_test``)
and auto-skips when the database is unreachable, so the default suite never
requires Docker. Run with ``make test-postgres``.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.models import Candle, Exchange, Market
from app.repositories.candles import CandleRepository

pytestmark = pytest.mark.postgres

BASE = datetime(2026, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


async def seed_market_with_candles(
    pg_session_factory,
    symbol: str,
    count: int,
) -> UUID:
    async with pg_session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
        )
        session.add(market)
        await session.flush()
        for hour in range(count):
            open_time = BASE + hour * HOUR
            session.add(
                Candle(
                    market_id=market.id,
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
        return market.id


async def test_postgres_candle_pagination(pg_session_factory) -> None:
    """Candle pagination behaves identically on PostgreSQL."""
    market_id = await seed_market_with_candles(pg_session_factory, "PGUSD", 5)
    repository = CandleRepository(pg_session_factory())

    total = await repository.count_candles(market_id=market_id, timeframe="1h")
    items = await repository.get_candles(
        market_id=market_id,
        timeframe="1h",
        limit=2,
        offset=1,
        start=None,
        end=None,
    )
    assert total == 5
    assert len(items) == 2
    assert items[0].open_time == BASE + HOUR


async def test_postgres_range_query(pg_session_factory) -> None:
    """The half-open range filter matches the SQLite behavior."""
    market_id = await seed_market_with_candles(pg_session_factory, "PGRNG", 5)
    repository = CandleRepository(pg_session_factory())

    items = await repository.get_candles(
        market_id=market_id,
        timeframe="1h",
        limit=100,
        offset=0,
        start=BASE + HOUR,
        end=BASE + 4 * HOUR,
    )
    assert len(items) == 3
    assert [item.open_time for item in items] == [
        BASE + HOUR,
        BASE + 2 * HOUR,
        BASE + 3 * HOUR,
    ]