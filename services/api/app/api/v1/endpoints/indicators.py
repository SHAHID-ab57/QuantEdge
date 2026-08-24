"""Technical indicator REST endpoints.

Two surfaces:

- ``GET /indicators`` and ``GET /indicators/{indicator}`` publish the
  registry as a catalogue, including each indicator's parameter specs, so a
  client can build a correct input form without hardcoding anything about
  any specific indicator.
- ``GET /markets/{symbol}/indicators/{indicator}`` runs one indicator over
  stored candles.

Indicator parameters are passed as ordinary query parameters
(``?period=20&source=close``) rather than a JSON body. They are read from
the raw query string because the accepted set is defined by the indicator
itself, not by this module — declaring them as typed FastAPI parameters
would mean editing this file for every new indicator, which is exactly the
coupling the registry exists to remove. Everything after the reserved keys
below is handed to the engine, which validates it against the indicator's
own specs and rejects anything unknown.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.dependencies.indicators import get_indicator_service
from app.schemas.indicators import (
    IndicatorCalculationResponse,
    IndicatorCatalogResponse,
    IndicatorDTO,
)
from app.services.indicators import IndicatorService

#: Query keys owned by this endpoint; everything else is an indicator parameter.
RESERVED_QUERY_KEYS = frozenset({"timeframe", "start", "end", "limit"})

router = APIRouter(tags=["indicators"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Invalid parameters, timeframe, range, or too little data",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_indicator_parameter": {
                        "summary": "Parameter out of range, unknown, or wrong type",
                        "value": {
                            "code": "invalid_indicator_parameter",
                            "detail": "Parameter 'period' must be >= 1, got 0",
                        },
                    },
                    "insufficient_data": {
                        "summary": "Range shorter than the indicator's warmup",
                        "value": {
                            "code": "insufficient_data",
                            "detail": (
                                "Indicator 'sma' needs at least 20 candles for these "
                                "parameters; only 5 are available in this range"
                            ),
                        },
                    },
                    "invalid_timeframe": {
                        "summary": "Unsupported timeframe",
                        "value": {
                            "code": "invalid_timeframe",
                            "detail": "Unsupported timeframe '7d'; supported: 1m, 3m, 5m, ...",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown indicator, unknown market, or no stored candles",
        "content": {
            "application/json": {
                "examples": {
                    "indicator_not_found": {
                        "summary": "Unknown indicator name",
                        "value": {
                            "code": "indicator_not_found",
                            "detail": (
                                "Indicator 'macd' is not registered; available: ema, rsi, sma"
                            ),
                        },
                    },
                    "market_not_found": {
                        "summary": "Unknown market symbol",
                        "value": {
                            "code": "market_not_found",
                            "detail": "Market 'NOPE' not found",
                        },
                    },
                }
            }
        },
    },
}

IndicatorServiceDep = Annotated[IndicatorService, Depends(get_indicator_service)]
SymbolPath = Annotated[str, Path(examples=["ETHUSD"], description="Market symbol")]
IndicatorPath = Annotated[
    str,
    Path(examples=["sma"], description="Registered indicator name"),
]


@router.get(
    "/indicators",
    response_model=IndicatorCatalogResponse,
    summary="List available indicators",
    description=(
        "Return every registered indicator with its parameter specifications "
        "and output series. A client can build a complete, correctly-constrained "
        "parameter form from this response alone."
    ),
)
async def list_indicators(service: IndicatorServiceDep) -> IndicatorCatalogResponse:
    """Return the indicator catalogue."""
    return service.list_indicators()


@router.get(
    "/indicators/{indicator}",
    response_model=IndicatorDTO,
    summary="Describe one indicator",
    description="Return a single indicator's metadata, parameters, and output series.",
    responses=_ERROR_RESPONSES,
)
async def describe_indicator(
    indicator: IndicatorPath,
    service: IndicatorServiceDep,
) -> IndicatorDTO:
    """Return one indicator's catalogue entry."""
    return service.get_indicator(indicator)


@router.get(
    "/markets/{symbol}/indicators/{indicator}",
    response_model=IndicatorCalculationResponse,
    summary="Calculate an indicator over stored candles",
    description=(
        "Run one indicator over the market's stored candles for a timeframe. "
        "Indicator parameters are supplied as query parameters "
        "(e.g. `?period=20&source=close`); anything the indicator does not "
        "declare is rejected rather than ignored. Returned series align "
        "index-for-index with `timestamps`, with `null` during the warmup "
        "period."
    ),
    responses=_ERROR_RESPONSES,
)
async def calculate_indicator(
    request: Request,
    symbol: SymbolPath,
    indicator: IndicatorPath,
    service: IndicatorServiceDep,
    timeframe: Annotated[
        str,
        Query(examples=["1h"], description="Candle resolution, e.g. 1m, 15m, 1h, 1d"),
    ],
    start: Annotated[
        datetime | None,
        Query(description="Inclusive start of the candle range (ISO-8601, UTC)"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="Exclusive end of the candle range (ISO-8601, UTC)"),
    ] = None,
    limit: Annotated[
        int | None,
        Query(ge=1, description="Maximum candles to analyze; defaults to the server page size"),
    ] = None,
) -> IndicatorCalculationResponse:
    """Calculate one indicator over one market/timeframe."""
    params = {
        key: value for key, value in request.query_params.items() if key not in RESERVED_QUERY_KEYS
    }
    return await service.calculate(
        symbol,
        indicator,
        timeframe=timeframe,
        params=params,
        start=start,
        end=end,
        limit=limit,
    )
