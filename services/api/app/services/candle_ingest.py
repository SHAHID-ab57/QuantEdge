"""Historical OHLCV candle ingestion from Delta Exchange India.

Fetches candles from ``GET /v2/history/candles``, validates and normalizes
each record, then persists them into ``candles`` in a single transaction.
Ingestion is idempotent: re-running the same range never duplicates rows
(the ``uq_candles_market_timeframe_open_time`` unique constraint is the
backstop). Invalid records are logged and rejected — never silently fixed.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine
from app.integrations.delta import CandleResponse, DeltaClient, get_delta_client
from app.models.candle import Candle
from app.models.exchange import Exchange
from app.models.market import Market

logger = logging.getLogger("app.services.candle_ingest")

EXCHANGE_SLUG = "delta"
CANDLE_SOURCE = "delta"

# Resolutions currently documented by Delta Exchange India (1w/2w/7d/30d were
# deprecated by Delta on 2025-10-18 and are intentionally unsupported).
DELTA_RESOLUTIONS = frozenset({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d"})

# Documented maximum candles per /v2/history/candles request; ranges longer
# than this are split into contiguous non-overlapping request windows.
DEFAULT_CANDLES_PER_REQUEST = 2000

_RESOLUTION_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


class CandleIngestError(RuntimeError):
    """Raised when candle ingestion cannot proceed safely."""


@dataclass(frozen=True)
class IngestReport:
    """Outcome of one candle ingestion run."""

    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    api_requests: int
    received: int
    accepted: int
    rejected: int
    inserted: int
    duplicates_skipped: int
    duration_seconds: float


async def ingest_candles(
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    max_candles_per_request: int = DEFAULT_CANDLES_PER_REQUEST,
    client: DeltaClient | None = None,
    session: AsyncSession | None = None,
) -> IngestReport:
    """Fetch, validate, and persist historical candles for one market.

    Args:
        symbol: The Delta market symbol as stored in ``markets`` (e.g. ``ETHUSDT``).
        timeframe: Candle resolution, e.g. ``1h``.
        start: Range start (inclusive), timezone-aware UTC.
        end: Range end (exclusive), timezone-aware UTC.
        max_candles_per_request: Cap on candles requested per API call;
            the documented Delta limit is 2000.
        client: Delta REST client; built from settings when omitted.
        session: Database session; built from the configured engine when
            omitted. Pass a session with no active transaction.

    Returns:
        A report with request/received/accepted/rejected/inserted/skipped
        counts and elapsed time.

    Raises:
        CandleIngestError: When the market is unknown, the timeframe is
            unsupported, or the requested range is invalid.
    """
    started_at = perf_counter()
    logger.info(
        "Candle ingestion started (symbol=%s timeframe=%s range=[%s, %s))",
        symbol,
        timeframe,
        start.isoformat(),
        end.isoformat(),
    )

    _validate_request(timeframe, start, end, max_candles_per_request)

    owns_session = session is None
    if session is None:
        engine = get_engine()
        if engine is None:
            raise RuntimeError("Database is not configured")
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()

    owns_client = client is None
    if client is None:
        client = get_delta_client()

    try:
        return await _run_ingest(
            client,
            session,
            symbol,
            timeframe,
            start,
            end,
            max_candles_per_request,
            started_at,
        )
    finally:
        if owns_client:
            await client.aclose()
        if owns_session:
            await session.close()


def _validate_request(
    timeframe: str,
    start: datetime,
    end: datetime,
    max_candles_per_request: int,
) -> None:
    """Fail fast on unsupported or unusable ingestion parameters."""
    if timeframe not in DELTA_RESOLUTIONS:
        supported = ", ".join(sorted(DELTA_RESOLUTIONS))
        raise CandleIngestError(
            f"Unsupported timeframe {timeframe!r}; Delta supports: {supported}"
        )
    if start.tzinfo is None or end.tzinfo is None:
        raise CandleIngestError("start and end must be timezone-aware datetimes")
    if end <= start:
        raise CandleIngestError("end must be after start")
    if max_candles_per_request < 1:
        raise CandleIngestError("max_candles_per_request must be positive")


async def _run_ingest(
    client: DeltaClient,
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    max_candles_per_request: int,
    started_at: float,
) -> IngestReport:
    """Orchestrate fetch -> validate -> persist, then report."""
    async with session.begin():
        market = await _resolve_market(session, symbol)
        existing_keys = await _load_existing_keys(session, market.id, timeframe)

    duration = resolution_duration(timeframe)
    windows = _request_windows(start, end, duration, max_candles_per_request)

    records: list[CandleResponse] = []
    api_requests = 0
    for window_start, window_end in windows:
        api_requests += 1
        logger.info(
            "Candle request %d/%d (symbol=%s timeframe=%s range=[%s, %s))",
            api_requests,
            len(windows),
            symbol,
            timeframe,
            window_start.isoformat(),
            window_end.isoformat(),
        )
        records.extend(
            await client.get_candles(
                symbol=symbol,
                resolution=timeframe,
                start=int(window_start.timestamp()),
                end=int(window_end.timestamp()),
            )
        )

    received = len(records)
    records.sort(key=lambda record: record.time)

    candles, rejected = _build_candles(
        symbol,
        market.id,
        timeframe,
        start,
        end,
        duration,
        records,
    )

    inserted, duplicates_skipped, db_rejected = await _persist_candles(
        session, market.id, timeframe, candles, existing_keys
    )
    rejected += db_rejected

    duration_seconds = perf_counter() - started_at
    logger.info(
        "Candle ingestion: requests=%d received=%d accepted=%d rejected=%d "
        "inserted=%d duplicates_skipped=%d in %.2fs",
        api_requests,
        received,
        len(candles),
        rejected,
        inserted,
        duplicates_skipped,
        duration_seconds,
    )
    logger.info("Candle ingestion completed (symbol=%s timeframe=%s)", symbol, timeframe)

    return IngestReport(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        api_requests=api_requests,
        received=received,
        accepted=len(candles),
        rejected=rejected,
        inserted=inserted,
        duplicates_skipped=duplicates_skipped,
        duration_seconds=duration_seconds,
    )


async def _resolve_market(session: AsyncSession, symbol: str) -> Market:
    """Return the Delta market for a symbol, or raise with guidance."""
    market = (
        await session.execute(
            select(Market)
            .join(Exchange, Market.exchange_id == Exchange.id)
            .where(Exchange.slug == EXCHANGE_SLUG, Market.symbol == symbol)
        )
    ).scalar_one_or_none()
    if market is None:
        raise CandleIngestError(
            f"Market {symbol!r} not found on exchange {EXCHANGE_SLUG!r}; "
            "run the market sync first (uv run python scripts/sync_markets.py)"
        )
    return market


async def _load_existing_keys(
    session: AsyncSession, market_id: uuid.UUID, timeframe: str
) -> set[datetime]:
    """Load open times already stored for this market/timeframe."""
    rows = await session.execute(
        select(Candle.open_time).where(
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
        )
    )
    return set(rows.scalars())


def resolution_duration(timeframe: str) -> timedelta:
    """Map a resolution string to its bucket duration (e.g. ``1h`` -> 3600s)."""
    amount = int(timeframe[:-1])
    seconds = _RESOLUTION_UNIT_SECONDS[timeframe[-1]] * amount
    return timedelta(seconds=seconds)


def _request_windows(
    start: datetime,
    end: datetime,
    duration: timedelta,
    max_candles_per_request: int,
) -> list[tuple[datetime, datetime]]:
    """Split ``[start, end)`` into contiguous non-overlapping request windows."""
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    step = int(duration.total_seconds()) * max_candles_per_request

    windows: list[tuple[datetime, datetime]] = []
    window_start = start_ts
    while window_start < end_ts:
        window_end = min(window_start + step, end_ts)
        windows.append(
            (datetime.fromtimestamp(window_start, UTC), datetime.fromtimestamp(window_end, UTC))
        )
        window_start = window_end
    return windows


def _build_candles(
    symbol: str,
    market_id: uuid.UUID,
    timeframe: str,
    start: datetime,
    end: datetime,
    duration: timedelta,
    records: Sequence[CandleResponse],
) -> tuple[list[Candle], int]:
    """Validate and normalize fetched records; return (candles, rejected)."""
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    duration_seconds = int(duration.total_seconds())
    now_ts = int(datetime.now(UTC).timestamp())

    candles: list[Candle] = []
    rejected = 0
    for record in records:
        if _validate_candle(
            symbol, record, start_ts, end_ts, duration_seconds, now_ts, timeframe
        ):
            open_time = datetime.fromtimestamp(record.time, UTC)
            candles.append(
                Candle(
                    market_id=market_id,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + duration,
                    open=record.open,
                    high=record.high,
                    low=record.low,
                    close=record.close,
                    volume=record.volume,
                    quote_volume=None,
                    trade_count=None,
                    source=CANDLE_SOURCE,
                )
            )
        else:
            rejected += 1
    return candles, rejected


def _validate_candle(
    symbol: str,
    record: CandleResponse,
    start_ts: int,
    end_ts: int,
    duration_seconds: int,
    now_ts: int,
    timeframe: str,
) -> bool:
    """Apply the record acceptance policy; log every rejection reason."""
    if record.time < start_ts or record.time >= end_ts:
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): outside requested range",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if record.time % duration_seconds != 0:
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): open time not "
            "aligned to buckets",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if record.time + duration_seconds > now_ts:
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): bucket not yet closed",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if not (record.high >= record.open and record.high >= record.close):
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): high is not dominant",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if not (record.low <= record.open and record.low <= record.close):
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): low is not dominant",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if record.high < record.low:
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): high below low",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if record.low < 0:
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): negative price",
            symbol,
            timeframe,
            record.time,
        )
        return False
    if record.volume < 0:
        logger.warning(
            "Rejecting candle (symbol=%s timeframe=%s time=%d): negative volume",
            symbol,
            timeframe,
            record.time,
        )
        return False
    return True


async def _persist_candles(
    session: AsyncSession,
    market_id: uuid.UUID,
    timeframe: str,
    candles: Sequence[Candle],
    existing_keys: set[datetime],
) -> tuple[int, int, int]:
    """Insert candles idempotently; return (inserted, duplicates_skipped, rejected).

    Records whose ``open_time`` already exists are skipped without touching
    the database. Rows that still fail at the database level (races or
    constraint violations) are isolated via savepoints, logged, and counted
    as rejected — never silently accepted.
    """
    pending: list[Candle] = []
    duplicates_skipped = 0
    for candle in candles:
        if candle.open_time in existing_keys:
            duplicates_skipped += 1
            continue
        existing_keys.add(candle.open_time)
        pending.append(candle)

    if not pending:
        return 0, duplicates_skipped, 0

    inserted = 0
    rejected = 0
    async with session.begin():
        for candle in pending:
            try:
                async with session.begin_nested():
                    session.add(candle)
                    await session.flush()
                inserted += 1
            except IntegrityError as exc:
                rejected += 1
                logger.warning(
                    "Rejecting candle (market_id=%s timeframe=%s open_time=%s): "
                    "rejected by the database (%s)",
                    market_id,
                    timeframe,
                    candle.open_time.isoformat(),
                    exc.orig,
                )

    return inserted, duplicates_skipped, rejected