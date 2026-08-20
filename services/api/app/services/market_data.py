"""Market data service — business logic for the market data REST API.

The service validates inputs, normalizes query parameters, calls the
repositories, and returns DTOs. Domain-specific errors are raised here;
routers never see ORM models or build queries.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi import status

from app.core.exceptions import AppError
from app.models.candle import TIMEFRAMES
from app.models.market import Market
from app.repositories.candles import SORT_COLUMNS, CandleRepository, CandleStats
from app.repositories.markets import MarketRepository
from app.schemas.market_data import (
    CandleDTO,
    CandlePageResponse,
    CandleQuality,
    CandleStatistics,
    CandleStatsResponse,
    LatestCandleResponse,
    MarketDTO,
    MarketListResponse,
    MarketResearchResponse,
    Pagination,
    QueryMetadata,
    ResearchTimeframeMetrics,
    TimeframesResponse,
)

logger = logging.getLogger("app.services.market_data")


class MarketNotFoundError(AppError):
    """Raised when the requested market symbol does not exist."""

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"Market {symbol!r} not found",
            code="market_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class CandleNotFoundError(AppError):
    """Raised when no candles exist for the requested market/timeframe."""

    def __init__(self, symbol: str, timeframe: str) -> None:
        super().__init__(
            f"No candles stored for market {symbol!r} and timeframe {timeframe!r}",
            code="candle_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidTimeframeError(AppError):
    """Raised when the timeframe is not supported by the platform."""

    def __init__(self, timeframe: str) -> None:
        super().__init__(
            f"Unsupported timeframe {timeframe!r}; supported: {', '.join(TIMEFRAMES)}",
            code="invalid_timeframe",
        )


class InvalidRangeError(AppError):
    """Raised when the requested candle range is unusable."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_range")


class LimitExceededError(AppError):
    """Raised when the page size exceeds the configured maximum."""

    def __init__(self, limit: int, max_limit: int) -> None:
        super().__init__(
            f"limit {limit} exceeds the configured maximum of {max_limit}",
            code="limit_exceeded",
        )


class InvalidSortError(AppError):
    """Raised when the sort column or direction is unsupported."""

    def __init__(self, sort: str, direction: str) -> None:
        columns = ", ".join(sorted(SORT_COLUMNS))
        super().__init__(
            f"Unsupported sort {sort!r} (direction {direction!r}); "
            f"supported columns: {columns}, directions: asc, desc",
            code="invalid_sort",
        )


MISSING_SAMPLE_MAX_BUCKETS = 200_000
MISSING_SAMPLE_LIMIT = 100


@dataclass(frozen=True)
class MarketDataService:
    """Business logic for reading validated market data."""

    candle_repository: CandleRepository
    market_repository: MarketRepository
    default_limit: int
    max_limit: int

    async def list_markets(self) -> MarketListResponse:
        """Return all available markets, ordered by symbol."""
        markets = await self.market_repository.get_all()
        return MarketListResponse(
            markets=[MarketDTO.model_validate(market) for market in markets],
            total=len(markets),
        )

    async def get_timeframes(self, symbol: str) -> TimeframesResponse:
        """Return the timeframes that have stored candles for a market."""
        market = await self._require_market(symbol)
        timeframes = await self.candle_repository.get_available_timeframes(market.id)
        return TimeframesResponse(symbol=symbol, timeframes=timeframes)

    async def get_research(self, symbol: str) -> MarketResearchResponse:
        """Return data-coverage research metrics for a market.

        Expected buckets are derived from the stored range ``[oldest, newest]``
        of each timeframe; missing candles are the difference between the
        expected contiguous bucket count and what is actually stored.
        """
        market = await self._require_market(symbol)
        rows = await self.candle_repository.get_research_metrics(market.id)

        per_timeframe: list[ResearchTimeframeMetrics] = []
        for timeframe, stored, oldest, newest in rows:
            per_timeframe.append(_research_timeframe(timeframe, stored, oldest, newest))

        oldest_at = min(
            (entry.oldest_at for entry in per_timeframe if entry.oldest_at is not None),
            default=None,
        )
        newest_at = max(
            (entry.newest_at for entry in per_timeframe if entry.newest_at is not None),
            default=None,
        )
        total_candles = sum(entry.stored_candles for entry in per_timeframe)
        logger.info(
            "Serving research metrics (symbol=%s timeframes=%d total=%d)",
            symbol,
            len(per_timeframe),
            total_candles,
        )
        return MarketResearchResponse(
            symbol=symbol,
            oldest_candle_at=oldest_at,
            newest_candle_at=newest_at,
            coverage_days=_coverage_days(oldest_at, newest_at),
            total_candles=total_candles,
            timeframes=per_timeframe,
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int,
        offset: int,
        sort: str = "open_time",
        direction: str = "asc",
    ) -> CandlePageResponse:
        """Return a page of candles plus backend-computed analytics.

        The range ``[start, end)`` is half-open; naive datetimes are treated
        as UTC. ``statistics`` and ``quality`` cover the full query range,
        ``meta`` reports server-side timing, and ``items`` are sorted by the
        whitelisted ``sort`` column in ``direction`` order.
        """
        market = await self._require_market(symbol)
        self._validate_timeframe(timeframe)
        start, end = self._validate_range(start, end)
        self._validate_limit(limit)
        self._validate_sort(sort, direction)

        started_at = perf_counter()
        db_started = perf_counter()
        candles = await self.candle_repository.get_candles(
            market.id,
            timeframe,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            sort=sort,
            direction=direction,
        )
        aggregates = await self.candle_repository.get_candle_stats(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        invalid_ohlc = await self.candle_repository.count_invalid_ohlc(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        duplicates = await self.candle_repository.count_duplicate_open_times(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        out_of_order = await self.candle_repository.count_out_of_order(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        missing_samples = await self._missing_interval_samples(
            market.id,
            timeframe,
            start=start,
            end=end,
            aggregates=aggregates,
        )
        database_time_ms = (perf_counter() - db_started) * 1000

        returned = len(candles)
        statistics, quality = _analytics(
            aggregates,
            invalid_ohlc,
            duplicates,
            out_of_order,
            missing_samples,
            timeframe=timeframe,
            now=datetime.now(UTC),
        )
        logger.info(
            "Serving candles (symbol=%s timeframe=%s limit=%d offset=%d total=%d "
            "sort=%s dir=%s db=%.1fms)",
            symbol,
            timeframe,
            limit,
            offset,
            aggregates.total_candles,
            sort,
            direction,
            database_time_ms,
        )
        return CandlePageResponse(
            symbol=symbol,
            timeframe=timeframe,
            items=[CandleDTO.model_validate(candle) for candle in candles],
            pagination=Pagination(
                total=aggregates.total_candles,
                returned=returned,
                has_more=offset + returned < aggregates.total_candles,
                limit=limit,
                offset=offset,
            ),
            statistics=statistics,
            quality=quality,
            meta=QueryMetadata(
                execution_time_ms=(perf_counter() - started_at) * 1000,
                database_time_ms=database_time_ms,
                rows_scanned=offset + returned,
                rows_returned=returned,
                cache_status="disabled",
                generated_at=datetime.now(UTC),
            ),
        )

    async def _missing_interval_samples(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None,
        end: datetime | None,
        aggregates: CandleStats,
    ) -> list[datetime]:
        """Sample the earliest missing buckets inside the observed span.

        The exact missing count comes from the aggregate math; this only
        produces up to ``MISSING_SAMPLE_LIMIT`` timestamps. When the span is
        too large to walk cheaply, an empty sample list is returned.
        """
        if (
            aggregates.total_candles == 0
            or aggregates.oldest_open is None
            or aggregates.newest_open is None
        ):
            return []
        duration_seconds = int(_timeframe_duration(timeframe).total_seconds())
        expected = _expected_buckets(
            aggregates.oldest_open,
            aggregates.newest_open,
            duration_seconds,
        )
        if expected > MISSING_SAMPLE_MAX_BUCKETS:
            return []
        present = {
            int(_as_utc(open_time).timestamp())
            for open_time in await self.candle_repository.get_open_times(
                market_id,
                timeframe,
                start=start,
                end=end,
            )
        }
        range_start = _snap_up(int(_as_utc(aggregates.oldest_open).timestamp()), duration_seconds)
        range_end = (
            _snap_down(int(_as_utc(aggregates.newest_open).timestamp()), duration_seconds)
            + duration_seconds
        )
        samples: list[datetime] = []
        timestamp = range_start
        while timestamp < range_end and len(samples) < MISSING_SAMPLE_LIMIT:
            if timestamp not in present:
                samples.append(datetime.fromtimestamp(timestamp, UTC))
            timestamp += duration_seconds
        return samples

    async def get_latest_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> LatestCandleResponse:
        """Return the most recent candle for a market/timeframe."""
        market = await self._require_market(symbol)
        self._validate_timeframe(timeframe)
        candle = await self.candle_repository.get_latest_candle(market.id, timeframe)
        if candle is None:
            raise CandleNotFoundError(symbol, timeframe)
        return LatestCandleResponse(
            symbol=symbol,
            timeframe=timeframe,
            candle=CandleDTO.model_validate(candle),
        )

    async def get_candle_stats(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> CandleStatsResponse:
        """Return aggregate statistics for candles in a market/timeframe.

        The range ``[start, end)`` is half-open; naive datetimes are treated
        as UTC. When no candles match, a 404 domain error is raised so callers
        can distinguish "no data" from a broken query.
        """
        market = await self._require_market(symbol)
        self._validate_timeframe(timeframe)
        start, end = self._validate_range(start, end)

        stats = await self.candle_repository.get_candle_stats(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        if stats.total_candles == 0:
            raise CandleNotFoundError(symbol, timeframe)

        first_candle = await self.candle_repository.get_first_candle(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        last_candle = await self.candle_repository.get_latest_candle(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        logger.info(
            "Serving candle stats (symbol=%s timeframe=%s start=%s end=%s total=%d)",
            symbol,
            timeframe,
            start,
            end,
            stats.total_candles,
        )
        return CandleStatsResponse(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            total_candles=stats.total_candles,
            highest_price=stats.highest_price,
            lowest_price=stats.lowest_price,
            average_volume=stats.average_volume,
            first_candle=CandleDTO.model_validate(first_candle) if first_candle else None,
            last_candle=CandleDTO.model_validate(last_candle) if last_candle else None,
        )

    async def _require_market(self, symbol: str) -> Market:
        """Resolve a symbol to a market, or raise a 404 domain error."""
        market = await self.market_repository.get_by_symbol(symbol)
        if market is None:
            raise MarketNotFoundError(symbol)
        return market

    def _validate_timeframe(self, timeframe: str) -> None:
        if timeframe not in TIMEFRAMES:
            raise InvalidTimeframeError(timeframe)

    def _validate_range(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        if (start is None) != (end is None):
            raise InvalidRangeError("start and end must be provided together")
        if start is None or end is None:
            return None, None
        start = _as_utc(start)
        end = _as_utc(end)
        if end <= start:
            raise InvalidRangeError("end must be after start")
        return start, end

    def _validate_limit(self, limit: int) -> None:
        if limit > self.max_limit:
            raise LimitExceededError(limit, self.max_limit)

    def _validate_sort(self, sort: str, direction: str) -> None:
        if sort not in SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidSortError(sort, direction)


def _as_utc(value: datetime) -> datetime:
    """Normalize to aware UTC; naive datetimes are treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _timeframe_duration(timeframe: str) -> timedelta:
    """Return the bucket duration of a supported timeframe."""
    amount = int(timeframe[:-1])
    unit = timeframe[-1]
    seconds = {"m": 60, "h": 3600, "d": 86400}[unit] * amount
    return timedelta(seconds=seconds)


def _snap_up(timestamp: int, step: int) -> int:
    """Round a timestamp up to the next epoch-aligned bucket start."""
    return ((timestamp + step - 1) // step) * step


def _snap_down(timestamp: int, step: int) -> int:
    """Round a timestamp down to the previous epoch-aligned bucket start."""
    return (timestamp // step) * step


def _expected_buckets(oldest: datetime, newest: datetime, duration_seconds: int) -> int:
    """Count expected buckets in the observed span ``[oldest, newest]``."""
    return int((newest - oldest).total_seconds() // duration_seconds) + 1


def _freshness_score(age_seconds: float | None) -> float:
    """Score the freshness of the newest candle (0-100).

    Mirrors the markets quality thresholds on a 100-point scale: under an
    hour is perfect, and the score decays to zero beyond 30 days.
    """
    if age_seconds is None:
        return 0.0
    if age_seconds < 3_600:
        return 100.0
    if age_seconds < 86_400:
        return 80.0
    if age_seconds < 7 * 86_400:
        return 50.0
    if age_seconds < 30 * 86_400:
        return 20.0
    return 0.0


def _analytics(
    aggregates: CandleStats,
    invalid_ohlc: int,
    duplicates: int,
    out_of_order: int,
    missing_samples: list[datetime],
    *,
    timeframe: str,
    now: datetime,
) -> tuple[CandleStatistics, CandleQuality]:
    """Derive statistics and quality from one aggregate query.

    Expected buckets, missing counts, and the overall quality score use the
    same semantics as the validation service: ``coverage * validity``.
    """
    total = aggregates.total_candles
    oldest = aggregates.oldest_open
    newest = aggregates.newest_open
    newest_close = aggregates.newest_close

    if total == 0 or oldest is None or newest is None:
        return (
            CandleStatistics(
                highest_price=None,
                lowest_price=None,
                highest_volume=None,
                lowest_volume=None,
                average_open=None,
                average_close=None,
                average_high=None,
                average_low=None,
                average_volume=None,
                total_candles=0,
                first_candle_at=None,
                last_candle_at=None,
                expected_candles=0,
                missing_candles=0,
                completeness=None,
            ),
            CandleQuality(
                completeness_score=0.0,
                freshness_score=0.0,
                missing_interval_count=0,
                missing_intervals=[],
                duplicate_candles=0,
                out_of_order_candles=0,
                invalid_ohlc_candles=0,
                gaps_detected=False,
                overall_quality_score=0.0,
            ),
        )

    duration_seconds = int(_timeframe_duration(timeframe).total_seconds())
    expected = _expected_buckets(oldest, newest, duration_seconds)
    missing = max(0, expected - total)
    completeness = round(100.0 * total / expected, 1)

    age_seconds = (
        max(0.0, (now - _as_utc(newest_close)).total_seconds())
        if newest_close is not None
        else None
    )
    freshness = _freshness_score(age_seconds)

    coverage = (expected - missing) / expected if expected else 0.0
    validity = (total - invalid_ohlc) / total if total else 0.0
    overall = round(100.0 * coverage * validity, 2)

    return (
        CandleStatistics(
            highest_price=aggregates.highest_price,
            lowest_price=aggregates.lowest_price,
            highest_volume=aggregates.highest_volume,
            lowest_volume=aggregates.lowest_volume,
            average_open=aggregates.average_open,
            average_close=aggregates.average_close,
            average_high=aggregates.average_high,
            average_low=aggregates.average_low,
            average_volume=aggregates.average_volume,
            total_candles=total,
            first_candle_at=oldest,
            last_candle_at=newest,
            expected_candles=expected,
            missing_candles=missing,
            completeness=completeness,
        ),
        CandleQuality(
            completeness_score=completeness,
            freshness_score=freshness,
            missing_interval_count=missing,
            missing_intervals=missing_samples,
            duplicate_candles=duplicates,
            out_of_order_candles=out_of_order,
            invalid_ohlc_candles=invalid_ohlc,
            gaps_detected=missing > 0,
            overall_quality_score=overall,
        ),
    )


def _coverage_days(
    oldest: datetime | None,
    newest: datetime | None,
) -> float | None:
    """Return the covered span in days (1 decimal), or ``None`` without data."""
    if oldest is None or newest is None:
        return None
    return round((newest - oldest).total_seconds() / 86_400, 1)


def _research_timeframe(
    timeframe: str,
    stored: int,
    oldest: datetime,
    newest: datetime,
) -> ResearchTimeframeMetrics:
    """Compute research metrics for one stored timeframe."""
    duration = _timeframe_duration(timeframe)
    expected = int((newest - oldest).total_seconds() // duration.total_seconds()) + 1
    missing = max(0, expected - stored)
    coverage_days = _coverage_days(oldest, newest)
    completeness = round(100.0 * stored / expected, 1) if expected > 0 else None
    average_daily = (
        round(stored / coverage_days, 1)
        if coverage_days is not None and coverage_days > 0
        else None
    )
    return ResearchTimeframeMetrics(
        timeframe=timeframe,
        stored_candles=stored,
        oldest_at=oldest,
        newest_at=newest,
        coverage_days=coverage_days,
        expected_candles=expected,
        missing_candles=missing,
        completeness=completeness,
        average_daily_candles=average_daily,
    )