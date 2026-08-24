"""Shared domain errors and validators for market-scoped queries.

Extracted from ``market_data.py`` once the indicator API needed the exact
same symbol/timeframe/range/limit checks: an indicator request is a market
data query with a calculation attached, and two copies of "is this
timeframe supported" would inevitably drift.

``market_data.py`` re-exports every error defined here, so existing imports
from that module continue to work unchanged.
"""

from datetime import UTC, datetime

from fastapi import status

from app.core.exceptions import AppError
from app.models.candle import TIMEFRAMES


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

    def __init__(self, sort: str, direction: str, columns: str) -> None:
        super().__init__(
            f"Unsupported sort {sort!r} (direction {direction!r}); "
            f"supported columns: {columns}, directions: asc, desc",
            code="invalid_sort",
        )


def as_utc(value: datetime) -> datetime:
    """Normalize to aware UTC; naive datetimes are treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_timeframe(timeframe: str) -> None:
    """Reject a timeframe the platform does not store candles for."""
    if timeframe not in TIMEFRAMES:
        raise InvalidTimeframeError(timeframe)


def normalize_range(
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Validate and UTC-normalize a half-open ``[start, end)`` range.

    Both bounds must be supplied together — a half-specified range is
    almost always a caller bug, and silently treating it as "all history"
    would return far more data than intended.
    """
    if (start is None) != (end is None):
        raise InvalidRangeError("start and end must be provided together")
    if start is None or end is None:
        return None, None
    start = as_utc(start)
    end = as_utc(end)
    if end <= start:
        raise InvalidRangeError("end must be after start")
    return start, end


def validate_limit(limit: int, max_limit: int) -> None:
    """Reject a page size above the configured server-side maximum."""
    if limit > max_limit:
        raise LimitExceededError(limit, max_limit)
