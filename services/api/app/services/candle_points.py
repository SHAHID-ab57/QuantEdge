"""Loading a market's candles as framework-free analysis points.

Extracted from ``IndicatorService`` once the Feature Engineering service
needed the identical sequence — resolve the market, validate the
timeframe/range/limit, run one ordered candle query, project the ORM rows
onto ``OHLCVPoint`` — because "load the candles an analysis will run over"
is one operation, not one per analytical context. Two copies would drift
the moment either side's validation changed.

``_to_point`` is the boundary that keeps every analytical engine free of
SQLAlchemy: nothing past this function sees an ORM object, which is what
lets the same indicator and feature code serve a future backtest or
training job whose candles come from somewhere else entirely.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from app.indicators.base import OHLCVPoint
from app.models.candle import Candle
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.services.market_query import (
    CandleNotFoundError,
    MarketNotFoundError,
    normalize_range,
    validate_limit,
    validate_timeframe,
)


@dataclass(frozen=True, slots=True)
class LoadedCandles:
    """Candles ready for an analytical engine, plus how long loading took."""

    points: list[OHLCVPoint]
    database_time_ms: float


async def load_candle_points(
    *,
    symbol: str,
    timeframe: str,
    market_repository: MarketRepository,
    candle_repository: CandleRepository,
    default_limit: int,
    max_limit: int,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> LoadedCandles:
    """Validate the request and load one market's candles as analysis points.

    The range ``[start, end)`` is half-open and naive datetimes are treated
    as UTC — the same contract ``GET /markets/{symbol}/candles`` uses.

    Raises ``MarketNotFoundError``, ``InvalidTimeframeError``,
    ``InvalidRangeError``, ``LimitExceededError``, or
    ``CandleNotFoundError`` — every one of them a shared domain error the
    application's existing handler already maps to a JSON envelope, so no
    caller needs analysis-specific error handling.
    """
    market = await market_repository.get_by_symbol(symbol)
    if market is None:
        raise MarketNotFoundError(symbol)
    validate_timeframe(timeframe)
    start, end = normalize_range(start, end)
    resolved_limit = default_limit if limit is None else limit
    validate_limit(resolved_limit, max_limit)

    db_started = perf_counter()
    candles = await candle_repository.get_candles(
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

    return LoadedCandles(
        points=[to_point(candle) for candle in candles],
        database_time_ms=database_time_ms,
    )


def to_point(candle: Candle) -> OHLCVPoint:
    """Project an ORM candle onto the engines' framework-free input type."""
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
