"""Market data service — business logic for the market data REST API.

The service validates inputs, normalizes query parameters, calls the
repositories, and returns DTOs. Domain-specific errors are raised here;
routers never see ORM models or build queries.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import status

from app.core.exceptions import AppError
from app.models.candle import TIMEFRAMES
from app.models.market import Market
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.market_data import (
    CandleDTO,
    CandlePageResponse,
    LatestCandleResponse,
    MarketDTO,
    MarketListResponse,
    Pagination,
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

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int,
        offset: int,
    ) -> CandlePageResponse:
        """Return a page of candles for a market/timeframe.

        The range ``[start, end)`` is half-open; naive datetimes are treated
        as UTC. Candles are sorted ascending by open time.
        """
        market = await self._require_market(symbol)
        self._validate_timeframe(timeframe)
        start, end = self._validate_range(start, end)
        self._validate_limit(limit)

        candles = await self.candle_repository.get_candles(
            market.id,
            timeframe,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        total = await self.candle_repository.count_candles(
            market.id,
            timeframe,
            start=start,
            end=end,
        )
        returned = len(candles)
        logger.info(
            "Serving candles (symbol=%s timeframe=%s limit=%d offset=%d total=%d)",
            symbol,
            timeframe,
            limit,
            offset,
            total,
        )
        return CandlePageResponse(
            symbol=symbol,
            timeframe=timeframe,
            items=[CandleDTO.model_validate(candle) for candle in candles],
            pagination=Pagination(
                total=total,
                returned=returned,
                has_more=offset + returned < total,
                limit=limit,
                offset=offset,
            ),
        )

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


def _as_utc(value: datetime) -> datetime:
    """Normalize to aware UTC; naive datetimes are treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)