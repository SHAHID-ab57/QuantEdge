"""Market data REST endpoints.

Exposes validated historical candle data from the ``candles`` table.
Read-only; no authentication, no streaming, no trading.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.market_data import get_market_data_service
from app.schemas.market_data import (
    CandlePageResponse,
    CandleStatsResponse,
    LatestCandleResponse,
    MarketListResponse,
    MarketResearchResponse,
    TimeframesResponse,
)
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/markets", tags=["markets"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Invalid timeframe, range, or limit",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_timeframe": {
                        "summary": "Unsupported timeframe",
                        "value": {
                            "code": "invalid_timeframe",
                            "detail": "Unsupported timeframe '7d'; supported: 1d, 1h, 1m, ...",
                        },
                    },
                    "invalid_range": {
                        "summary": "Range misuse",
                        "value": {
                            "code": "invalid_range",
                            "detail": "end must be after start",
                        },
                    },
                    "limit_exceeded": {
                        "summary": "Page size too large",
                        "value": {
                            "code": "limit_exceeded",
                            "detail": "limit 5000 exceeds the configured maximum of 1000",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown market or no stored candles",
        "content": {
            "application/json": {
                "examples": {
                    "market_not_found": {
                        "summary": "Unknown market symbol",
                        "value": {
                            "code": "market_not_found",
                            "detail": "Market 'NOPE' not found",
                        },
                    },
                    "candle_not_found": {
                        "summary": "No candles for market/timeframe",
                        "value": {
                            "code": "candle_not_found",
                            "detail": "No candles stored for market 'ETHUSD' and timeframe '1h'",
                        },
                    },
                }
            }
        },
    },
}

MarketDataServiceDep = Annotated[MarketDataService, Depends(get_market_data_service)]
SymbolPath = Annotated[str, Path(examples=["ETHUSD"], description="Market symbol")]
TimeframeQuery = Annotated[
    str,
    Query(examples=["1h"], description="Candle resolution, e.g. 1m, 15m, 1h, 1d"),
]


@router.get(
    "",
    response_model=MarketListResponse,
    summary="List available markets",
    description="Return all markets currently tracked by the platform, ordered by symbol.",
    responses=_ERROR_RESPONSES,
)
async def list_markets(
    service: MarketDataServiceDep,
) -> MarketListResponse:
    """Return all available markets."""
    return await service.list_markets()


@router.get(
    "/{symbol}/timeframes",
    response_model=TimeframesResponse,
    summary="List timeframes with stored candle data",
    description=(
        "Return the distinct timeframes that have at least one stored candle "
        "for the market (empty list when none)."
    ),
    responses=_ERROR_RESPONSES,
)
async def list_timeframes(
    symbol: SymbolPath,
    service: MarketDataServiceDep,
) -> TimeframesResponse:
    """Return the timeframes that have stored candles for a market."""
    return await service.get_timeframes(symbol)


@router.get(
    "/{symbol}/research",
    response_model=MarketResearchResponse,
    summary="Research metrics for stored candle coverage",
    description=(
        "Return per-timeframe coverage metrics for a market: stored candle "
        "count, oldest/newest candle, covered span in days, expected bucket "
        "count, missing candles, completeness percentage, and average daily "
        "candles. Expected buckets are derived from the stored range of each "
        "timeframe; empty when the market has no candles."
    ),
    responses=_ERROR_RESPONSES,
)
async def get_research(
    symbol: SymbolPath,
    service: MarketDataServiceDep,
) -> MarketResearchResponse:
    """Return data-coverage research metrics for a market."""
    return await service.get_research(symbol)


@router.get(
    "/{symbol}/candles",
    response_model=CandlePageResponse,
    summary="Query historical candles",
    description=(
        "Return candles for a market/timeframe sorted by a whitelisted "
        "column. The range [start, end) is half-open; dates may be ISO-8601 "
        "datetimes (naive values are treated as UTC). Omit start/end to "
        "query all history. Every response embeds backend-computed "
        "statistics, data-quality metrics, and query metadata for the full "
        "range. Pages use limit/offset with total/returned/has_more metadata."
    ),
    responses=_ERROR_RESPONSES,
)
async def get_candles(
    symbol: SymbolPath,
    timeframe: TimeframeQuery,
    service: MarketDataServiceDep,
    start: Annotated[
        datetime | None,
        Query(
            examples=["2026-08-14T00:00:00Z"],
            description="Range start (inclusive), ISO-8601 UTC",
        ),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(
            examples=["2026-08-17T00:00:00Z"],
            description="Range end (exclusive), ISO-8601 UTC",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().candles_max_limit,
            description="Maximum candles per page",
        ),
    ] = get_settings().candles_default_limit,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of candles to skip"),
    ] = 0,
    sort: Annotated[
        str,
        Query(
            examples=["open_time"],
            description="Sort column; one of open_time, open, high, low, close, volume",
        ),
    ] = "open_time",
    dir: Annotated[
        str,
        Query(examples=["asc"], description="Sort direction; asc or desc"),
    ] = "asc",
) -> CandlePageResponse:
    """Return a page of candles plus backend analytics for the range."""
    return await service.get_candles(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        sort=sort,
        direction=dir,
    )


@router.get(
    "/{symbol}/latest",
    response_model=LatestCandleResponse,
    summary="Get the latest candle",
    description="Return the candle with the newest open time for a market/timeframe.",
    responses=_ERROR_RESPONSES,
)
async def get_latest_candle(
    symbol: SymbolPath,
    timeframe: TimeframeQuery,
    service: MarketDataServiceDep,
) -> LatestCandleResponse:
    """Return the most recent candle for a market/timeframe."""
    return await service.get_latest_candle(symbol, timeframe)


@router.get(
    "/{symbol}/candles/stats",
    response_model=CandleStatsResponse,
    summary="Candle statistics for a range",
    description=(
        "Return aggregate statistics (count, highest/lowest price, average "
        "volume, first and last candle) for a market/timeframe over the "
        "half-open range [start, end). Omit start/end for all history; "
        "raises 404 when no candles match."
    ),
    responses=_ERROR_RESPONSES,
)
async def get_candle_stats(
    symbol: SymbolPath,
    timeframe: TimeframeQuery,
    service: MarketDataServiceDep,
    start: Annotated[
        datetime | None,
        Query(
            examples=["2026-08-14T00:00:00Z"],
            description="Range start (inclusive), ISO-8601 UTC",
        ),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(
            examples=["2026-08-17T00:00:00Z"],
            description="Range end (exclusive), ISO-8601 UTC",
        ),
    ] = None,
) -> CandleStatsResponse:
    """Return aggregate candle statistics for a market/timeframe range."""
    return await service.get_candle_stats(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
    )