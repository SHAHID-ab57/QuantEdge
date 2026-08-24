"""Exponential Moving Average — the reference *recursive* indicator.

Included alongside SMA because it exercises a different shape of the
contract: the value at each point depends on the previous value, so the
implementation must carry state across the loop and must define how that
state is seeded. Anyone adding a stateful indicator (MACD, ATR, ADX)
should follow this file rather than ``sma.py``.
"""

from collections.abc import Mapping
from typing import Any

from app.indicators.base import (
    Indicator,
    IndicatorContext,
    IndicatorMetadata,
    IndicatorOutput,
    SeriesSpec,
)
from app.indicators.builtin.common import (
    period_parameter,
    period_warmup,
    single_series_output,
    source_parameter,
)
from app.indicators.registry import register


@register
class ExponentialMovingAverage(Indicator):
    """Exponentially weighted mean, seeded from the first full SMA window."""

    metadata = IndicatorMetadata(
        name="ema",
        label="Exponential Moving Average",
        description=(
            "A moving average that weights recent candles more heavily, so it "
            "reacts faster than an SMA of the same period at the cost of being "
            "noisier. Seeded from the first full simple average of the period, "
            "the conventional choice."
        ),
        category="trend",
        parameters=(
            period_parameter(description="Smoothing period; the multiplier is 2 / (period + 1)."),
            source_parameter(description="Which price of each candle to smooth."),
        ),
        outputs=(
            SeriesSpec(
                name="ema",
                label="EMA",
                description="The exponentially weighted average.",
            ),
        ),
        version="1.0.0",
        author="Eth AI Platform",
        complexity="O(n) — one recursive pass over the candle range after an O(period) seed.",
        warmup_description="Equal to the period parameter.",
        aliases=("Exponential MA", "Exponentially Weighted Moving Average"),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        """The SMA seed needs a full window before the recursion can start."""
        return period_warmup(params)

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Seed with an SMA, then apply the standard EMA recurrence.

        Numerical stability note: unlike SMA's running sum, this recursion
        genuinely does carry floating-point error forward indefinitely —
        each point is computed from the *previous computed point*, not
        re-derived from the source data, so any rounding at step ``t``
        remains part of every value from ``t`` onward (attenuated by the
        multiplier each step, but never fully purged). This is an accepted,
        well-known property of the EMA formula itself, not a bug in this
        implementation; IEEE-754 double precision keeps the drift far below
        anything visible at the six-significant-digit precision this
        platform displays, even over a series of hundreds of thousands of
        candles (see ``test_repeated_calculation_is_bit_for_bit_deterministic``).
        """
        period = ctx.int_param("period")
        values = ctx.source_values()
        multiplier = 2.0 / (period + 1.0)

        out: list[float | None] = [None] * len(values)
        seed_index = period - 1
        previous = sum(values[:period]) / period
        out[seed_index] = previous

        for index in range(period, len(values)):
            previous = (values[index] - previous) * multiplier + previous
            out[index] = previous

        return single_series_output("ema", f"EMA({period})", out)
