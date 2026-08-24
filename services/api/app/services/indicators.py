"""Indicator service — the bridge between stored candles and the engine.

This is the only place the two halves meet: the engine knows nothing about
markets, timeframes, or the database, and the repositories know nothing
about indicators. Keeping the join here is what lets the same engine be
driven later by a replay session or a backtest runner that has candles from
somewhere else entirely.

Routers never touch SQL, and the engine never touches the ORM — both
platform conventions hold.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from app.indicators.base import OHLCVPoint
from app.indicators.engine import ENGINE_VERSION, IndicatorEngine
from app.indicators.errors import (
    IndicatorExecutionError,
    IndicatorNotFoundError,
    InsufficientDataError,
    InvalidIndicatorParameterError,
)
from app.models.candle import Candle
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.indicators import (
    IndicatorBatchItemRequest,
    IndicatorBatchItemResult,
    IndicatorBatchResponse,
    IndicatorCalculationMeta,
    IndicatorCalculationResponse,
    IndicatorCatalogResponse,
    IndicatorDTO,
    IndicatorSeriesDTO,
)
from app.services.market_query import (
    CandleNotFoundError,
    MarketNotFoundError,
    normalize_range,
    validate_limit,
    validate_timeframe,
)

logger = logging.getLogger("app.services.indicators")

#: Per-indicator errors a batch item can fail with independently of its siblings.
_BATCH_ITEM_ERRORS = (
    IndicatorNotFoundError,
    InvalidIndicatorParameterError,
    InsufficientDataError,
    IndicatorExecutionError,
)


@dataclass(frozen=True)
class IndicatorService:
    """Business logic for the indicator REST API."""

    candle_repository: CandleRepository
    market_repository: MarketRepository
    engine: IndicatorEngine
    default_limit: int
    max_limit: int

    def list_indicators(self) -> IndicatorCatalogResponse:
        """Return the full indicator catalogue.

        Reads straight from the registry, so an indicator added to
        ``app/indicators/builtin/`` appears here with no change to this
        service.
        """
        metadata = self.engine.describe_all()
        indicators = [IndicatorDTO.from_metadata(entry) for entry in metadata]
        categories = sorted({entry.category for entry in metadata})
        return IndicatorCatalogResponse(
            indicators=indicators,
            total=len(indicators),
            categories=categories,
        )

    def get_indicator(self, name: str) -> IndicatorDTO:
        """Return one indicator's metadata, or raise ``IndicatorNotFoundError``."""
        return IndicatorDTO.from_metadata(self.engine.describe(name))

    async def calculate(
        self,
        symbol: str,
        indicator: str,
        *,
        timeframe: str,
        params: dict[str, object],
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> IndicatorCalculationResponse:
        """Load candles for a market/timeframe and run one indicator over them.

        The range ``[start, end)`` is half-open and naive datetimes are
        treated as UTC — the same contract as ``GET /markets/{symbol}/candles``.
        """
        points, database_time_ms = await self._load_points(symbol, timeframe, start, end, limit)

        run = self.engine.run(indicator, points, params)

        logger.info(
            "Calculated indicator (symbol=%s timeframe=%s indicator=%s candles=%d "
            "cache=%s db=%.1fms calc=%.1fms)",
            symbol,
            timeframe,
            indicator,
            len(points),
            run.cache_status,
            database_time_ms,
            run.execution_time_ms,
        )
        return IndicatorCalculationResponse(
            symbol=symbol,
            timeframe=timeframe,
            indicator=IndicatorDTO.from_metadata(run.metadata),
            parameters=run.params,
            timestamps=[point.open_time for point in points],
            series=[IndicatorSeriesDTO.from_series(series) for series in run.output.series],
            meta=IndicatorCalculationMeta(
                candles_analyzed=len(points),
                warmup_candles=run.warmup,
                execution_time_ms=run.execution_time_ms,
                database_time_ms=database_time_ms,
                cache_status=run.cache_status,
                generated_at=datetime.now(UTC),
            ),
        )

    async def calculate_batch(
        self,
        symbol: str,
        *,
        timeframe: str,
        requests: list[IndicatorBatchItemRequest],
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> IndicatorBatchResponse:
        """Run several indicators over one shared candle load — the chart overlay API.

        Candles are loaded exactly **once** here and handed to every
        requested indicator, rather than the client issuing N separate
        calculation requests that would each redundantly reload the same
        range — the whole point of this endpoint over N calls to
        ``calculate``, and what makes "add another overlay" cheap at chart
        scale.

        Each item's outcome is independent: a bad parameter on one
        indicator becomes that item's ``error_code``/``error_detail``
        rather than failing the batch, so a chart showing four correctly
        configured overlays isn't blocked by a fifth, misconfigured one.
        Every successful item still runs through the engine's own result
        cache (``IndicatorEngine``'s ``IndicatorCache``), so re-requesting
        an unchanged overlay after only one other overlay's parameters
        changed is served from cache, not recomputed.
        """
        points, database_time_ms = await self._load_points(symbol, timeframe, start, end, limit)
        timestamps = [point.open_time for point in points]

        results = [self._run_batch_item(item, points) for item in requests]

        return IndicatorBatchResponse(
            symbol=symbol,
            timeframe=timeframe,
            timestamps=timestamps,
            results=results,
            candles_analyzed=len(points),
            database_time_ms=database_time_ms,
            engine_version=ENGINE_VERSION,
            generated_at=datetime.now(UTC),
        )

    def _run_batch_item(
        self,
        item: IndicatorBatchItemRequest,
        points: list[OHLCVPoint],
    ) -> IndicatorBatchItemResult:
        """Run one batch entry, converting any of its own domain errors into a per-item failure."""
        try:
            run = self.engine.run(item.indicator, points, item.params)
        except _BATCH_ITEM_ERRORS as exc:
            return IndicatorBatchItemResult(
                indicator=item.indicator,
                success=False,
                error_code=exc.code,
                error_detail=exc.message,
            )
        return IndicatorBatchItemResult(
            indicator=item.indicator,
            success=True,
            label=run.metadata.label,
            parameters=run.params,
            series=[IndicatorSeriesDTO.from_series(series) for series in run.output.series],
            cache_status=run.cache_status,
            warmup_candles=run.warmup,
            execution_time_ms=run.execution_time_ms,
        )

    async def _load_points(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        limit: int | None,
    ) -> tuple[list[OHLCVPoint], float]:
        """Validate the request and load one market's candles as engine-ready points.

        Shared by ``calculate`` and ``calculate_batch`` — the market
        lookup, timeframe/range/limit validation, and the single candle
        query are identical between "run one indicator" and "run several
        indicators over the same range," so this is the one place that
        logic lives.
        """
        market = await self.market_repository.get_by_symbol(symbol)
        if market is None:
            raise MarketNotFoundError(symbol)
        validate_timeframe(timeframe)
        start, end = normalize_range(start, end)
        resolved_limit = self.default_limit if limit is None else limit
        validate_limit(resolved_limit, self.max_limit)

        db_started = perf_counter()
        candles = await self.candle_repository.get_candles(
            market.id,
            timeframe,
            start=start,
            end=end,
            limit=resolved_limit,
            offset=0,
            sort="open_time",
            direction="asc",
        )
        database_time_ms = (perf_counter() - db_started) * 1000

        if not candles:
            raise CandleNotFoundError(symbol, timeframe)

        return [_to_point(candle) for candle in candles], database_time_ms


def _to_point(candle: Candle) -> OHLCVPoint:
    """Project an ORM candle onto the engine's framework-free input type.

    This is the boundary that keeps indicators free of SQLAlchemy: nothing
    past this function sees an ORM object.
    """
    open_time = candle.open_time
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=UTC)
    return OHLCVPoint(
        open_time=open_time,
        open=float(candle.open),
        high=float(candle.high),
        low=float(candle.low),
        close=float(candle.close),
        volume=float(candle.volume),
    )
