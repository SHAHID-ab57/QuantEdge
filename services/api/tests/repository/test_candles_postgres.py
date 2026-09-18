"""PostgreSQL-backed repository tests (opt-in profile).

Marked ``postgres``: the fixture reads ``TEST_DATABASE_URL`` (defaulting
to ``postgresql+asyncpg://research:research@localhost:5432/eth_platform_test``)
and auto-skips when the database is unreachable, so the default suite never
requires Docker. Run with ``make test-postgres``.

Every ``pg_session_factory()`` call here is wrapped in ``async with`` —
found the hard way, not by inspection, that a bare, never-closed session
(``CandleRepository(pg_session_factory())``, the pattern every test in
this file originally used) deadlocks ``postgres_engine``'s own teardown:
its ``DROP SCHEMA ... CASCADE`` waits forever for a lock a leaked,
still-open session connection never releases. This had never actually
run in this environment before — ``TEST_DATABASE_URL`` always pointed at
an unreachable database (auth failure against the wrong Postgres
instance), so every test here always auto-skipped, and the leak never
had a real database to hang against. First confirmed reachable, and
first actually hung on, during the investigation that produced this
file's newest two tests.
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
    async with pg_session_factory() as session:
        repository = CandleRepository(session)
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


async def test_postgres_count_duplicate_open_times_is_always_zero(pg_session_factory) -> None:
    """Structurally guaranteed zero — see the method's own docstring.

    Regression coverage for the fix that stopped this from running a real
    GROUP BY .. HAVING query on every request: proves the schema's own
    ``uq_candles_market_timeframe_open_time`` constraint really does make
    this always 0 against a real Postgres instance (not just SQLite, whose
    constraint enforcement can differ), not that the method merely claims it.
    """
    market_id = await seed_market_with_candles(pg_session_factory, "PGDUP", 5)
    async with pg_session_factory() as session:
        repository = CandleRepository(session)
        result = await repository.count_duplicate_open_times(market_id=market_id, timeframe="1h")
    assert result == 0


async def test_postgres_count_out_of_order_still_detects_real_violations(
    pg_session_factory,
) -> None:
    """The planner-hint optimization must not silently change what this returns.

    Regression coverage for the fix that scopes ``SET enable_seqscan/
    bitmapscan = off`` around this query's own execution (see the method's
    docstring for why): the whole point of forcing a different plan is
    that it returns the *same* answer faster, never a different one. Seeds
    one genuinely out-of-order candle (its open_time falls before the
    previous candle's close_time) against a real Postgres instance and
    confirms it's still caught.
    """
    async with pg_session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol="PGOOO",
            base_asset="PGO",
            quote_asset="USD",
            market_type="perpetual",
        )
        session.add(market)
        await session.flush()
        # Candle 1: 00:00-01:30 (closes late, overlapping candle 2's open).
        # Candle 2: opens 01:00, before candle 1's own close_time — out of order.
        # Candle 3: 02:00-03:00, a normal, non-overlapping candle.
        rows = [
            (BASE, BASE + timedelta(hours=1, minutes=30)),
            (BASE + HOUR, BASE + 2 * HOUR),
            (BASE + 2 * HOUR, BASE + 3 * HOUR),
        ]
        for open_time, close_time in rows:
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=close_time,
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
        market_id = market.id

    async with pg_session_factory() as session:
        repository = CandleRepository(session)
        result = await repository.count_out_of_order(market_id=market_id, timeframe="1h")
    assert result == 1


async def test_postgres_range_query(pg_session_factory) -> None:
    """The half-open range filter matches the SQLite behavior."""
    market_id = await seed_market_with_candles(pg_session_factory, "PGRNG", 5)
    async with pg_session_factory() as session:
        repository = CandleRepository(session)
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
