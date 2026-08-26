"""Shared candle-construction helpers for the ML Dataset Builder's tests."""

from datetime import UTC, datetime, timedelta

from app.features.base import OHLCVPoint

__all__ = ["candles"]


def candles(count: int, *, start_price: float = 100.0) -> list[OHLCVPoint]:
    """An ascending, strictly-increasing-price candle series, one per hour.

    Deliberately monotonically increasing (`close == start_price + i`) so a
    target's correctness can be checked by simple arithmetic against the
    row index, rather than needing a second, independent computation of
    "what should this target equal."
    """
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVPoint(
            open_time=base + timedelta(hours=i),
            open=start_price + i,
            high=start_price + i + 5,
            low=start_price + i - 5,
            close=start_price + i,
            volume=10.0 + i,
        )
        for i in range(count)
    ]
