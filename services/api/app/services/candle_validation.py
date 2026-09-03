"""Read-only market data quality validation for stored OHLCV candles.

Checks the integrity of stored candle data before it is consumed by APIs,
feature engineering, or AI models: duplicates, gaps, OHLC relationships,
volume sign, bucket alignment, UTC timestamps, and chronological ordering.
The service never writes to the database.

Validation rules
----------------
- ``high >= open``, ``high >= close``, ``low <= open``, ``low <= close``,
  ``high >= low`` (OHLC dominance).
- ``volume >= 0`` and ``quote_volume >= 0`` when present.
- ``open_time`` aligned to timeframe buckets (e.g. ``:00`` and ``:30`` for
  30m; the Unix epoch is the alignment origin).
- ``close_time == open_time + duration``.
- Timestamps are UTC (aware timestamps must have zero UTC offset; naive
  timestamps are treated as UTC — SQLite returns naive values, PostgreSQL
  returns aware values).
- Candles are chronologically ordered and never overlap: each candle's
  ``open_time`` must be >= the previous candle's ``close_time``. Candles in
  the same bucket (e.g. ``12:00`` and ``12:30`` for 1h) are counted as
  duplicate buckets.
- Exact duplicates on the unique key ``(market_id, timeframe, open_time)``
  are structurally impossible (constraint backstop); a defensive GROUP BY
  query still verifies this.

Range semantics
---------------
When ``start``/``end`` are omitted, validation covers the observed span:
from the oldest stored candle to the newest candle plus one bucket duration.
When given, the range snaps to whole buckets (epoch-aligned) — expected
candles are every bucket start in ``[start, end)``.

Quality score
-------------
``coverage = (expected - missing) / expected`` (0 when nothing is expected)
``validity  = (total - invalid) / total``            (0 when empty)
``quality_score = 100 * coverage * validity``         (percent, 2 dp)
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine
from app.models.candle import TIMEFRAMES, Candle
from app.models.exchange import Exchange
from app.models.market import Market
from app.services.candle_ingest import resolution_duration

logger = logging.getLogger("app.services.candle_validation")

EXCHANGE_SLUG = "delta"

DEFAULT_ISSUE_LIMIT = 100


class CandleValidationError(RuntimeError):
    """Raised when validation cannot proceed safely."""


@dataclass(frozen=True)
class CandleIssue:
    """One stored candle that failed one or more validation checks."""

    open_time: datetime
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of one market data quality validation run."""

    symbol: str
    timeframe: str
    start: datetime | None
    end: datetime | None
    total_candles: int
    expected_candles: int
    missing_candles: int
    duplicate_count: int
    invalid_candles: int
    coverage_percent: float
    validity_percent: float
    quality_score: float
    duration_seconds: float
    issues: tuple[CandleIssue, ...]
    missing_timestamps: tuple[datetime, ...]


async def validate_candles(
    *,
    symbol: str,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
    issue_limit: int = DEFAULT_ISSUE_LIMIT,
    session: AsyncSession | None = None,
) -> ValidationReport:
    """Validate the stored candle data for one market/timeframe.

    Args:
        symbol: The market symbol as stored in ``markets`` (e.g. ``ETHUSDT``).
        timeframe: Candle resolution, e.g. ``1h``.
        start: Optional validation range start (inclusive); the observed
            span of stored candles is used when omitted.
        end: Optional validation range end (exclusive).
        issue_limit: Cap on issue and missing-timestamp samples reported
            (counts are always exact).
        session: Database session; built from the configured engine when
            omitted. The session is never modified.

    Returns:
        A report with totals, gap/duplicate/invalid counts, quality score,
        elapsed time, and sampled issues.

    Raises:
        CandleValidationError: When the market is unknown, the timeframe is
            unsupported, or the requested range is invalid.
    """
    started_at = perf_counter()
    logger.info(
        "Validation started (symbol=%s timeframe=%s%s)",
        symbol,
        timeframe,
        (
            f" range=[{start.isoformat()}, {end.isoformat()})"
            if start is not None and end is not None
            else " range=observed-span"
        ),
    )

    _validate_request(timeframe, start, end, issue_limit)

    owns_session = session is None
    if session is None:
        engine = get_engine()
        if engine is None:
            raise RuntimeError("Database is not configured")
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()

    try:
        market = await _resolve_market(session, symbol)
        duration_seconds = int(resolution_duration(timeframe).total_seconds())

        rows = list(
            (
                await session.execute(
                    select(Candle)
                    .where(
                        Candle.market_id == market.id,
                        Candle.timeframe == timeframe,
                    )
                    .order_by(Candle.open_time)
                )
            )
            .scalars()
            .all()
        )

        range_start, range_end = _validation_range(start, end, rows, duration_seconds)

        if range_start is None or range_end is None:
            report = _empty_report(symbol, timeframe, started_at)
            logger.warning(
                "Validation found no candles for (symbol=%s timeframe=%s)",
                symbol,
                timeframe,
            )
        else:
            exact_duplicates = await _count_exact_duplicates(session, market.id, timeframe)
            issues, invalid_count, overlaps = _assess_candles(rows, duration_seconds, issue_limit)
            expected, missing, missing_samples = _find_gaps(
                rows, range_start, range_end, duration_seconds, issue_limit
            )
            report = _build_report(
                symbol=symbol,
                timeframe=timeframe,
                range_start=range_start,
                range_end=range_end,
                rows=rows,
                expected=expected,
                missing=missing,
                exact_duplicates=exact_duplicates,
                overlaps=overlaps,
                invalid_count=invalid_count,
                issues=issues,
                missing_samples=missing_samples,
                started_at=started_at,
            )

        logger.info(
            "Validation completed (symbol=%s timeframe=%s): total=%d expected=%d "
            "missing=%d duplicates=%d invalid=%d quality=%.2f%% in %.2fs",
            symbol,
            timeframe,
            report.total_candles,
            report.expected_candles,
            report.missing_candles,
            report.duplicate_count,
            report.invalid_candles,
            report.quality_score,
            report.duration_seconds,
        )
        if report.missing_candles:
            logger.warning(
                "Validation found %d missing candle(s) (symbol=%s timeframe=%s)",
                report.missing_candles,
                symbol,
                timeframe,
            )
        if report.duplicate_count:
            logger.warning(
                "Validation found %d duplicate/overlapping record(s) (symbol=%s timeframe=%s)",
                report.duplicate_count,
                symbol,
                timeframe,
            )
        if report.invalid_candles:
            logger.warning(
                "Validation found %d invalid candle(s) (symbol=%s timeframe=%s)",
                report.invalid_candles,
                symbol,
                timeframe,
            )
        return report
    finally:
        if owns_session:
            await session.close()


def _validate_request(
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    issue_limit: int,
) -> None:
    """Fail fast on unsupported or unusable validation parameters."""
    if timeframe not in TIMEFRAMES:
        supported = ", ".join(TIMEFRAMES)
        raise CandleValidationError(
            f"Unsupported timeframe {timeframe!r}; supported timeframes: {supported}"
        )
    if (start is None) != (end is None):
        raise CandleValidationError("start and end must be given together")
    if start is not None and (start.tzinfo is None or end is None or end.tzinfo is None):
        raise CandleValidationError("start and end must be timezone-aware datetimes")
    if start is not None and end is not None and end <= start:
        raise CandleValidationError("end must be after start")
    if issue_limit < 1:
        raise CandleValidationError("issue_limit must be positive")


async def _resolve_market(session: AsyncSession, symbol: str) -> Market:
    """Return the market for a symbol, or raise with guidance."""
    market = (
        await session.execute(
            select(Market)
            .join(Exchange, Market.exchange_id == Exchange.id)
            .where(Exchange.slug == EXCHANGE_SLUG, Market.symbol == symbol)
        )
    ).scalar_one_or_none()
    if market is None:
        raise CandleValidationError(
            f"Market {symbol!r} not found on exchange {EXCHANGE_SLUG!r}; "
            "run the market sync first (uv run python scripts/sync_markets.py)"
        )
    return market


def _validation_range(
    start: datetime | None,
    end: datetime | None,
    rows: list[Candle],
    duration_seconds: int,
) -> tuple[int | None, int | None]:
    """Snap the validation range to whole buckets; return epoch seconds.

    Returns ``(None, None)`` when there are no candles and no explicit range.
    """
    if start is not None and end is not None:
        range_start = _snap_up(int(start.timestamp()), duration_seconds)
        range_end = _snap_down(int(end.timestamp()), duration_seconds)
        if range_end <= range_start:
            raise CandleValidationError(
                "Requested range contains no whole timeframe buckets; "
                f"expected buckets are epoch-aligned ({duration_seconds}s)"
            )
        return range_start, range_end
    if not rows:
        return None, None
    min_ts = int(min(_utc(row.open_time).timestamp() for row in rows))
    max_ts = int(max(_utc(row.open_time).timestamp() for row in rows))
    return _snap_up(min_ts, duration_seconds), max_ts + duration_seconds


def _snap_up(ts: int, step: int) -> int:
    """Round a timestamp up to the next epoch-aligned bucket start."""
    return ((ts + step - 1) // step) * step


def _snap_down(ts: int, step: int) -> int:
    """Round a timestamp down to the previous epoch-aligned bucket start."""
    return (ts // step) * step


def _assess_candles(
    rows: list[Candle],
    duration_seconds: int,
    issue_limit: int,
) -> tuple[dict[datetime, tuple[str, ...]], int, int]:
    """Check every candle; return (issues, invalid_count, overlaps)."""
    issues: dict[datetime, tuple[str, ...]] = {}
    invalid_count = 0
    overlaps = 0
    previous_open: datetime | None = None
    previous_close: datetime | None = None
    for candle in rows:
        reasons = list(_candle_reasons(candle, duration_seconds))
        open_time = _utc(candle.open_time)
        close_time = _utc(candle.close_time)
        if previous_open is not None and open_time < previous_open:
            reasons.append("not chronologically ordered")
        if previous_close is not None and open_time < previous_close:
            reasons.append("overlaps previous bucket")
            overlaps += 1
        if reasons:
            invalid_count += 1
            if len(issues) < issue_limit:
                issues[open_time] = tuple(reasons)
        previous_open = open_time
        previous_close = close_time
    return issues, invalid_count, overlaps


def _candle_reasons(candle: Candle, duration_seconds: int) -> tuple[str, ...]:
    """Return the validation rule violations for one candle."""
    open_time = _utc(candle.open_time)
    close_time = _utc(candle.close_time)
    reasons: list[str] = []
    if not (candle.high >= candle.open and candle.high >= candle.close):
        reasons.append("high is not dominant (high < open or high < close)")
    if not (candle.low <= candle.open and candle.low <= candle.close):
        reasons.append("low is not dominant (low > open or low > close)")
    if candle.high < candle.low:
        reasons.append("high below low")
    if candle.volume < 0:
        reasons.append("negative volume")
    if candle.quote_volume is not None and candle.quote_volume < 0:
        reasons.append("negative quote volume")
    if int(open_time.timestamp()) % duration_seconds != 0:
        reasons.append("open_time not aligned to timeframe buckets")
    if close_time - open_time != timedelta(seconds=duration_seconds):
        reasons.append("close_time does not match timeframe duration")
    if not (_is_utc(candle.open_time) and _is_utc(candle.close_time)):
        reasons.append("timestamp is not UTC")
    return tuple(reasons)


def _is_utc(value: datetime) -> bool:
    """Aware timestamps must be UTC; naive timestamps are treated as UTC."""
    if value.tzinfo is None:
        return True
    return value.utcoffset() == timedelta(0)


def _utc(value: datetime) -> datetime:
    """Normalize to aware UTC; naive timestamps are treated as UTC.

    SQLite returns naive datetimes while PostgreSQL returns aware ones; the
    alignment math must never depend on the local timezone of the host.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _count_exact_duplicates(
    session: AsyncSession,
    market_id: object,
    timeframe: str,
) -> int:
    """Count records violating the unique key (defensive; expect 0)."""
    subquery = (
        select(Candle.open_time)
        .where(Candle.market_id == market_id, Candle.timeframe == timeframe)
        .group_by(Candle.open_time)
        .having(func.count() > 1)
        .subquery()
    )
    return (await session.execute(select(func.count()).select_from(subquery))).scalar_one()


def _find_gaps(
    rows: list[Candle],
    range_start: int,
    range_end: int,
    duration_seconds: int,
    issue_limit: int,
) -> tuple[int, int, tuple[datetime, ...]]:
    """Count missing buckets in ``[range_start, range_end)`` and sample them.

    Returns ``(expected, missing, samples)``.
    """
    present = {int(_utc(row.open_time).timestamp()) for row in rows}
    expected = 0
    missing = 0
    samples: list[datetime] = []
    ts = range_start
    while ts < range_end:
        expected += 1
        if ts not in present:
            missing += 1
            if len(samples) < issue_limit:
                samples.append(datetime.fromtimestamp(ts, UTC))
        ts += duration_seconds
    return expected, missing, tuple(samples)


def _build_report(
    *,
    symbol: str,
    timeframe: str,
    range_start: int,
    range_end: int,
    rows: list[Candle],
    expected: int,
    missing: int,
    exact_duplicates: int,
    overlaps: int,
    invalid_count: int,
    issues: dict[datetime, tuple[str, ...]],
    missing_samples: tuple[datetime, ...],
    started_at: float,
) -> ValidationReport:
    """Assemble the report and compute the quality score."""
    total = len(rows)
    coverage = (expected - missing) / expected if expected else 0.0
    validity = (total - invalid_count) / total if total else 0.0
    return ValidationReport(
        symbol=symbol,
        timeframe=timeframe,
        start=datetime.fromtimestamp(range_start, UTC),
        end=datetime.fromtimestamp(range_end, UTC),
        total_candles=total,
        expected_candles=expected,
        missing_candles=missing,
        duplicate_count=exact_duplicates + overlaps,
        invalid_candles=invalid_count,
        coverage_percent=round(100 * coverage, 2),
        validity_percent=round(100 * validity, 2),
        quality_score=round(100 * coverage * validity, 2),
        duration_seconds=perf_counter() - started_at,
        issues=tuple(
            CandleIssue(open_time=open_time, reasons=reasons)
            for open_time, reasons in issues.items()
        ),
        missing_timestamps=missing_samples,
    )


def _empty_report(symbol: str, timeframe: str, started_at: float) -> ValidationReport:
    """Report for a market/timeframe with no stored candles."""
    return ValidationReport(
        symbol=symbol,
        timeframe=timeframe,
        start=None,
        end=None,
        total_candles=0,
        expected_candles=0,
        missing_candles=0,
        duplicate_count=0,
        invalid_candles=0,
        coverage_percent=0.0,
        validity_percent=0.0,
        quality_score=0.0,
        duration_seconds=perf_counter() - started_at,
        issues=(),
        missing_timestamps=(),
    )
