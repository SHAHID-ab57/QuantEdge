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
from app.indicators.engine import IndicatorEngine
from app.models.candle import Candle
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.indicators import (
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

        Candles are loaded in ascending open-time order because every
        indicator's math assumes chronological input; that ordering is not a
        caller-tunable option here, unlike on the candles endpoint.
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

        points = [_to_point(candle) for candle in candles]
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
