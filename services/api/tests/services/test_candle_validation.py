"""Tests for the market data quality validation service.

Validation runs read-only against an in-memory SQLite database with seeded
markets and hand-built candle rows (SQLite enforces the same unique key and
check constraints as PostgreSQL).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Candle, Exchange, Market
from app.services.candle_validation import (
    CandleValidationError,
    ValidationReport,
    _is_utc,
    validate_candles,
)

SessionFactory = async_sessionmaker[AsyncSession]

BASE = datetime(2026, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def utc(hour: int) -> datetime:
    """Epoch-aligned 1h bucket start on 2026-01-01 UTC."""
    return BASE + timedelta(hours=hour)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """In-memory SQLite engine with the market data schema applied.

    CHECK constraints are ignored so that deliberately-invalid rows
    (negative volume, bad OHLC) can be stored — validation must catch data
    that entered through any path, not just constraint-abiding inserts.
    The unique key on (market_id, timeframe, open_time) still applies.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _ignore_check_constraints(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA ignore_check_constraints = ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> SessionFactory:
    """Session factory bound to the test engine."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def seed_market(session_factory: SessionFactory, symbol: str = "ETHUSDT") -> uuid.UUID:
    """Create the Delta exchange and one market; return the market id."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset="ETH",
            quote_asset="USDT",
            market_type="spot",
        )
        session.add(market)
        await session.commit()
        return market.id


async def store_candles(
    session_factory: SessionFactory,
    market_id: uuid.UUID,
    open_times: list[datetime],
    *,
    timeframe: str = "1h",
    open: str = "3050.50",
    high: str = "3060.00",
    low: str = "3040.00",
    close: str = "3055.25",
    volume: str = "120.5",
) -> None:
    """Insert valid candles for the given bucket starts."""
    async with session_factory() as session:
        existing = set((await session.execute(select(Candle.open_time))).scalars())
        for open_time in open_times:
            if open_time in existing:
                continue
            session.add(
                Candle(
                    market_id=market_id,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + HOUR,
                    open=Decimal(open),
                    high=Decimal(high),
                    low=Decimal(low),
                    close=Decimal(close),
                    volume=Decimal(volume),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


async def validate(
    session_factory: SessionFactory,
    symbol: str = "ETHUSDT",
    timeframe: str = "1h",
    **kwargs,
) -> ValidationReport:
    """Run validation against the test fixtures."""
    return await validate_candles(
        symbol=symbol, timeframe=timeframe, session=session_factory(), **kwargs
    )


@pytest.mark.asyncio
async def test_perfect_dataset_scores_100(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0), utc(1), utc(2)])

    report = await validate(session_factory)

    assert report.total_candles == 3
    assert report.expected_candles == 3
    assert report.missing_candles == 0
    assert report.duplicate_count == 0
    assert report.invalid_candles == 0
    assert report.issues == ()
    assert report.missing_timestamps == ()
    assert report.coverage_percent == 100.0
    assert report.validity_percent == 100.0
    assert report.quality_score == 100.0


@pytest.mark.asyncio
async def test_missing_candle_in_middle_is_detected(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0), utc(1), utc(3), utc(4)])

    report = await validate(session_factory)

    assert report.total_candles == 4
    assert report.expected_candles == 5
    assert report.missing_candles == 1
    assert report.missing_timestamps == (utc(2),)


@pytest.mark.asyncio
async def test_invalid_ohlc_relationship_is_flagged(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0)])
    await store_candles(
        session_factory,
        market_id,
        [utc(1)],
        high="3040.00",
        low="3060.00",
        open="3050.00",
        close="3055.00",
    )

    report = await validate(session_factory)

    assert report.invalid_candles == 1
    (issue,) = report.issues
    assert issue.open_time == utc(1)
    reasons = " ".join(issue.reasons)
    assert "high is not dominant" in reasons
    assert "low is not dominant" in reasons
    assert "high below low" in reasons


@pytest.mark.asyncio
async def test_negative_volume_is_flagged(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0)])
    await store_candles(session_factory, market_id, [utc(1)], volume="-5")

    report = await validate(session_factory)

    assert report.invalid_candles == 1
    (issue,) = report.issues
    assert issue.open_time == utc(1)
    assert "negative volume" in issue.reasons


@pytest.mark.asyncio
async def test_same_bucket_candles_are_duplicates(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0)])
    misaligned = BASE + timedelta(minutes=30)
    await store_candles(session_factory, market_id, [misaligned])

    report = await validate(session_factory)

    assert report.duplicate_count == 1
    assert report.invalid_candles == 1
    (issue,) = report.issues
    assert issue.open_time == misaligned
    assert "overlaps previous bucket" in issue.reasons
    assert "open_time not aligned to timeframe buckets" in issue.reasons


@pytest.mark.asyncio
async def test_empty_dataset_scores_zero(session_factory: SessionFactory) -> None:
    await seed_market(session_factory)

    report = await validate(session_factory)

    assert report.total_candles == 0
    assert report.expected_candles == 0
    assert report.missing_candles == 0
    assert report.duplicate_count == 0
    assert report.invalid_candles == 0
    assert report.quality_score == 0.0
    assert report.coverage_percent == 0.0
    assert report.validity_percent == 0.0
    assert report.start is None
    assert report.end is None


@pytest.mark.asyncio
async def test_close_time_mismatch_is_flagged(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    async with session_factory() as session:
        session.add(
            Candle(
                market_id=market_id,
                timeframe="1h",
                open_time=utc(0),
                close_time=utc(0) + timedelta(minutes=45),
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

    report = await validate(session_factory)

    assert report.invalid_candles == 1
    (issue,) = report.issues
    assert "close_time does not match timeframe duration" in issue.reasons


@pytest.mark.asyncio
async def test_scoped_range_limits_validation(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0), utc(1), utc(2), utc(3)])

    report = await validate(session_factory, start=utc(1), end=utc(3))

    assert report.start == utc(1)
    assert report.end == utc(3)
    assert report.total_candles == 4
    assert report.expected_candles == 2
    assert report.missing_candles == 0


@pytest.mark.asyncio
async def test_issue_limit_caps_samples(session_factory: SessionFactory) -> None:
    market_id = await seed_market(session_factory)
    await store_candles(session_factory, market_id, [utc(0)])
    async with session_factory() as session:
        for hour in range(1, 5):
            session.add(
                Candle(
                    market_id=market_id,
                    timeframe="1h",
                    open_time=utc(hour),
                    close_time=utc(hour) + HOUR,
                    open=Decimal("3050.50"),
                    high=Decimal("3060.00"),
                    low=Decimal("3040.00"),
                    close=Decimal("3055.25"),
                    volume=Decimal("-1"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()

    report = await validate(session_factory, issue_limit=2)

    assert report.invalid_candles == 4
    assert len(report.issues) == 2


@pytest.mark.asyncio
async def test_unknown_market_raises_with_guidance(session_factory: SessionFactory) -> None:
    with pytest.raises(CandleValidationError, match="not found"):
        await validate_candles(symbol="NOPE", timeframe="1h", session=session_factory())


@pytest.mark.asyncio
async def test_unsupported_timeframe_raises(session_factory: SessionFactory) -> None:
    await seed_market(session_factory)
    with pytest.raises(CandleValidationError, match="timeframe"):
        await validate_candles(symbol="ETHUSDT", timeframe="7d", session=session_factory())


@pytest.mark.asyncio
async def test_invalid_range_raises(session_factory: SessionFactory) -> None:
    await seed_market(session_factory)
    with pytest.raises(CandleValidationError, match="end must be after start"):
        await validate_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=utc(2),
            end=utc(1),
            session=session_factory(),
        )


def test_is_utc() -> None:
    assert _is_utc(datetime(2026, 1, 1, tzinfo=UTC))
    assert _is_utc(datetime(2026, 1, 1))
    assert _is_utc(datetime(2026, 1, 1, tzinfo=UTC))


def test_is_utc_rejects_non_utc_offset() -> None:
    shifted = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert not _is_utc(shifted)
