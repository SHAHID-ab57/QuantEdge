"""Tests for the historical candle ingestion service.

The Delta API is mocked with ``httpx.MockTransport``; persistence is
exercised against an in-memory SQLite database.
"""

import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.integrations.delta import APIError, DeltaClient
from app.integrations.delta.config import DeltaConfig
from app.models import Candle, Exchange, Market
from app.services.candle_ingest import (
    DEFAULT_CANDLES_PER_REQUEST,
    CandleIngestError,
    _persist_candles,
    ingest_candles,
)

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
SessionFactory = async_sessionmaker[AsyncSession]

BASE_URL = "https://api.india.delta.exchange"

BASE = datetime(2026, 1, 1, tzinfo=UTC)
BASE_TS = int(BASE.timestamp())
HOUR = 3600


def client_for(handler: Handler) -> DeltaClient:
    """Build a Delta client over a mocked transport."""
    transport = httpx.MockTransport(handler)
    return DeltaClient(
        DeltaConfig(base_url=BASE_URL, api_key="", api_secret="", request_timeout=5.0),
        transport=transport,
    )


def make_candle(
    time: int,
    *,
    open: str = "3050.50",
    high: str = "3060.00",
    low: str = "3040.00",
    close: str = "3055.25",
    volume: str = "120.5",
) -> dict[str, int | str]:
    """Build a Delta ``/v2/history/candles`` payload entry."""
    return {
        "time": time,
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


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


async def count_candles(session: AsyncSession) -> int:
    """Count all candle rows."""
    return (await session.execute(select(func.count()).select_from(Candle))).scalar_one()


async def load_candles(session: AsyncSession) -> list[Candle]:
    """Load all candles ordered by open time."""
    return list((await session.execute(select(Candle).order_by(Candle.open_time))).scalars())


def as_utc(value: datetime) -> datetime:
    """Normalize a stored datetime to a tz-aware UTC value (SQLite is naive)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@pytest.mark.asyncio
async def test_ingest_normalizes_and_inserts_with_chunked_requests(
    session_factory: SessionFactory,
) -> None:
    """Candles are fetched in windowed requests, sorted, and persisted in UTC."""
    market_id = await seed_market(session_factory)
    captured: dict[str, list[str]] = {"urls": []}

    all_candles = [
        make_candle(BASE_TS + 0 * HOUR),
        make_candle(BASE_TS + 1 * HOUR),
        make_candle(BASE_TS + 2 * HOUR),
        make_candle(BASE_TS + 3 * HOUR),
        make_candle(BASE_TS + 4 * HOUR),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["urls"].append(str(request.url))
        query = {
            key: values[0] for key, values in parse_qs(urlparse(str(request.url)).query).items()
        }
        start = int(query["start"])
        end = int(query["end"])
        window = [candle for candle in all_candles if start <= int(candle["time"]) < end]
        window.reverse()
        return httpx.Response(200, json={"success": True, "result": window})

    client = client_for(handler)
    report = await ingest_candles(
        symbol="ETHUSDT",
        timeframe="1h",
        start=BASE,
        end=BASE + timedelta(hours=5),
        max_candles_per_request=2,
        client=client,
        session=session_factory(),
    )

    assert report.api_requests == 3
    assert report.received == 5
    assert report.accepted == 5
    assert report.rejected == 0
    assert report.inserted == 5
    assert report.duplicates_skipped == 0
    assert report.symbol == "ETHUSDT"
    assert report.timeframe == "1h"

    windows = [parse_qs(urlparse(url).query) for url in captured["urls"]]
    assert [int(w["start"][0]) for w in windows] == [
        BASE_TS,
        BASE_TS + 2 * HOUR,
        BASE_TS + 4 * HOUR,
    ]
    assert [int(w["end"][0]) for w in windows] == [
        BASE_TS + 2 * HOUR,
        BASE_TS + 4 * HOUR,
        BASE_TS + 5 * HOUR,
    ]

    async with session_factory() as session:
        candles = await load_candles(session)
        assert len(candles) == 5
        assert all(candle.market_id == market_id for candle in candles)
        assert [candle.open_time for candle in candles] == sorted(
            candle.open_time for candle in candles
        )
        first = candles[0]
        assert first.timeframe == "1h"
        assert as_utc(first.open_time) == datetime.fromtimestamp(BASE_TS, UTC)
        assert as_utc(first.close_time) == datetime.fromtimestamp(BASE_TS + HOUR, UTC)
        assert first.open == Decimal("3050.50")
        assert first.high == Decimal("3060.00")
        assert first.low == Decimal("3040.00")
        assert first.close == Decimal("3055.25")
        assert first.volume == Decimal("120.5")
        assert first.quote_volume is None
        assert first.trade_count is None
        assert first.source == "delta"


@pytest.mark.asyncio
async def test_malformed_record_fails_ingestion(session_factory: SessionFactory) -> None:
    """A record with a non-numeric price fails validation and persists nothing."""
    await seed_market(session_factory)
    payload = [make_candle(BASE_TS, open="not-a-number")]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": payload})

    client = client_for(handler)
    with pytest.raises(APIError):
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE,
            end=BASE + timedelta(hours=1),
            client=client,
            session=session_factory(),
        )

    async with session_factory() as session:
        assert await count_candles(session) == 0


@pytest.mark.asyncio
async def test_invalid_ohlc_values_are_rejected(session_factory: SessionFactory) -> None:
    """Records with impossible OHLC values are logged and skipped."""
    await seed_market(session_factory)
    payload = [
        make_candle(BASE_TS + 0 * HOUR, high="3000.00", low="3000.00"),
        make_candle(BASE_TS + 1 * HOUR, open="100.00", close="50.00", low="80.00"),
        make_candle(BASE_TS + 2 * HOUR, open="50.00", close="100.00", high="80.00"),
        make_candle(BASE_TS + 3 * HOUR, high="90.00", low="100.00"),
        make_candle(BASE_TS + 4 * HOUR, volume="-1"),
        make_candle(BASE_TS + 5 * HOUR, low="-5"),
        make_candle(BASE_TS + 6 * HOUR),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": payload})

    client = client_for(handler)
    report = await ingest_candles(
        symbol="ETHUSDT",
        timeframe="1h",
        start=BASE,
        end=BASE + timedelta(hours=7),
        client=client,
        session=session_factory(),
    )

    assert report.received == 7
    assert report.accepted == 1
    assert report.rejected == 6
    assert report.inserted == 1

    async with session_factory() as session:
        candles = await load_candles(session)
        assert len(candles) == 1
        assert as_utc(candles[0].open_time) == datetime.fromtimestamp(BASE_TS + 6 * HOUR, UTC)


@pytest.mark.asyncio
async def test_invalid_timestamps_are_rejected(session_factory: SessionFactory) -> None:
    """Out-of-range, unaligned, and not-yet-closed buckets are rejected."""
    await seed_market(session_factory)
    now = datetime.now(UTC)
    now_ts = int(now.timestamp())
    current_bucket = now_ts - (now_ts % HOUR)
    start = datetime.fromtimestamp(current_bucket - 2 * HOUR, UTC)
    end = datetime.fromtimestamp(current_bucket + 2 * HOUR, UTC)

    payload = [
        make_candle(-100),
        make_candle(current_bucket),
        make_candle(current_bucket + HOUR),
        make_candle(current_bucket - HOUR + 60),
        make_candle(current_bucket - HOUR),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": payload})

    client = client_for(handler)
    report = await ingest_candles(
        symbol="ETHUSDT",
        timeframe="1h",
        start=start,
        end=end,
        client=client,
        session=session_factory(),
    )

    assert report.received == 5
    assert report.rejected == 4
    assert report.accepted == 1
    assert report.inserted == 1

    async with session_factory() as session:
        candles = await load_candles(session)
        assert len(candles) == 1
        assert as_utc(candles[0].open_time) == datetime.fromtimestamp(current_bucket - HOUR, UTC)


@pytest.mark.asyncio
async def test_duplicate_candles_are_skipped_idempotently(
    session_factory: SessionFactory,
) -> None:
    """Re-ingesting the same range inserts nothing and reports duplicates."""
    await seed_market(session_factory)
    payload = [make_candle(BASE_TS + 0 * HOUR), make_candle(BASE_TS + 0 * HOUR)]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": payload})

    client = client_for(handler)
    first = await ingest_candles(
        symbol="ETHUSDT",
        timeframe="1h",
        start=BASE,
        end=BASE + timedelta(hours=1),
        client=client,
        session=session_factory(),
    )
    second = await ingest_candles(
        symbol="ETHUSDT",
        timeframe="1h",
        start=BASE,
        end=BASE + timedelta(hours=1),
        client=client,
        session=session_factory(),
    )

    assert first.inserted == 1
    assert first.duplicates_skipped == 1
    assert second.inserted == 0
    assert second.duplicates_skipped == 1

    async with session_factory() as session:
        assert await count_candles(session) == 1


@pytest.mark.asyncio
async def test_empty_response_is_valid(session_factory: SessionFactory) -> None:
    """An empty result inserts nothing and produces a clean report."""
    await seed_market(session_factory)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": []})

    client = client_for(handler)
    report = await ingest_candles(
        symbol="ETHUSDT",
        timeframe="1h",
        start=BASE,
        end=BASE + timedelta(hours=1),
        client=client,
        session=session_factory(),
    )

    assert report.received == 0
    assert report.accepted == 0
    assert report.inserted == 0

    async with session_factory() as session:
        assert await count_candles(session) == 0


@pytest.mark.asyncio
async def test_api_failure_persists_nothing(session_factory: SessionFactory) -> None:
    """A failed API response aborts ingestion with no partial writes."""
    await seed_market(session_factory)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "error": {"code": 601, "message": "Not found"}},
        )

    client = client_for(handler)
    with pytest.raises(APIError):
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE,
            end=BASE + timedelta(hours=1),
            client=client,
            session=session_factory(),
        )

    async with session_factory() as session:
        assert await count_candles(session) == 0


@pytest.mark.asyncio
async def test_partial_batch_failure_rolls_back_everything(
    session_factory: SessionFactory,
) -> None:
    """When one of several requests fails, no candles are persisted."""
    await seed_market(session_factory)
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 2:
            return httpx.Response(
                200,
                json={"success": False, "error": {"message": "boom"}},
            )
        return httpx.Response(
            200,
            json={"success": True, "result": [make_candle(BASE_TS)]},
        )

    client = client_for(handler)
    with pytest.raises(APIError):
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE,
            end=BASE + timedelta(hours=5),
            max_candles_per_request=1,
            client=client,
            session=session_factory(),
        )

    assert calls["count"] == 2
    async with session_factory() as session:
        assert await count_candles(session) == 0


@pytest.mark.asyncio
async def test_database_conflict_is_isolated_and_rejected(
    session_factory: SessionFactory,
) -> None:
    """Rows that collide at the database level are rejected, not silently kept."""
    market_id = await seed_market(session_factory)
    existing_time = datetime.fromtimestamp(BASE_TS + HOUR, UTC)

    async with session_factory() as session:
        session.add(
            Candle(
                market_id=market_id,
                timeframe="1h",
                open_time=existing_time,
                close_time=existing_time + timedelta(hours=1),
                open=Decimal("1"),
                high=Decimal("2"),
                low=Decimal("1"),
                close=Decimal("2"),
                volume=Decimal("1"),
                source="delta",
            )
        )
        await session.commit()

    conflicting = Candle(
        market_id=market_id,
        timeframe="1h",
        open_time=existing_time,
        close_time=existing_time + timedelta(hours=1),
        open=Decimal("9"),
        high=Decimal("9"),
        low=Decimal("9"),
        close=Decimal("9"),
        volume=Decimal("9"),
        source="delta",
    )
    fresh = Candle(
        market_id=market_id,
        timeframe="1h",
        open_time=datetime.fromtimestamp(BASE_TS + 2 * HOUR, UTC),
        close_time=datetime.fromtimestamp(BASE_TS + 3 * HOUR, UTC),
        open=Decimal("3"),
        high=Decimal("4"),
        low=Decimal("3"),
        close=Decimal("4"),
        volume=Decimal("1"),
        source="delta",
    )

    async with session_factory() as session:
        inserted, duplicates_skipped, rejected = await _persist_candles(
            session, market_id, "1h", [conflicting, fresh], set()
        )

    assert inserted == 1
    assert duplicates_skipped == 0
    assert rejected == 1

    async with session_factory() as session:
        assert await count_candles(session) == 2
        candles = await load_candles(session)
        assert {float(candle.open) for candle in candles} == {1.0, 3.0}


@pytest.mark.asyncio
async def test_unknown_symbol_raises_with_guidance(session_factory: SessionFactory) -> None:
    """A missing market fails fast and points at the market sync command."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no API call expected")

    client = client_for(handler)
    with pytest.raises(CandleIngestError) as excinfo:
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE,
            end=BASE + timedelta(hours=1),
            client=client,
            session=session_factory(),
        )

    message = str(excinfo.value)
    assert "ETHUSDT" in message
    assert "sync_markets" in message


@pytest.mark.asyncio
async def test_unsupported_timeframe_raises_before_any_request(
    session_factory: SessionFactory,
) -> None:
    """Deprecated or unknown resolutions fail fast without calling the API."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no API call expected")

    client = client_for(handler)
    with pytest.raises(CandleIngestError) as excinfo:
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1w",
            start=BASE,
            end=BASE + timedelta(days=7),
            client=client,
            session=session_factory(),
        )

    assert "1w" in str(excinfo.value)
    assert "1h" in str(excinfo.value)


@pytest.mark.asyncio
async def test_invalid_range_raises(session_factory: SessionFactory) -> None:
    """A reversed or zero-length range is rejected up front."""
    with pytest.raises(CandleIngestError):
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE + timedelta(hours=1),
            end=BASE,
            session=session_factory(),
        )
    with pytest.raises(CandleIngestError):
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE,
            end=BASE,
            session=session_factory(),
        )
    with pytest.raises(CandleIngestError):
        await ingest_candles(
            symbol="ETHUSDT",
            timeframe="1h",
            start=BASE,
            end=BASE + timedelta(hours=1),
            max_candles_per_request=0,
            session=session_factory(),
        )


@pytest.mark.asyncio
async def test_default_candles_per_request_is_documented_limit() -> None:
    """The default request cap matches the documented Delta API limit."""
    assert DEFAULT_CANDLES_PER_REQUEST == 2000
