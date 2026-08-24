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
    IndicatorSeries,
    SeriesSpec,
)
from app.indicators.builtin.sma import PRICE_SOURCES
from app.indicators.params import ParameterSpec
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
            ParameterSpec(
                name="period",
                type="int",
                label="Period",
                description="Smoothing period; the multiplier is 2 / (period + 1).",
                default=20,
                minimum=1,
                maximum=1000,
            ),
            ParameterSpec(
                name="source",
                type="string",
                label="Source",
                description="Which price of each candle to smooth.",
                default="close",
                choices=PRICE_SOURCES,
            ),
        ),
        outputs=(
            SeriesSpec(
                name="ema",
                label="EMA",
                description="The exponentially weighted average.",
            ),
        ),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        """The SMA seed needs a full window before the recursion can start."""
        return int(params["period"])

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Seed with an SMA, then apply the standard EMA recurrence."""
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

        return IndicatorOutput(
            series=[IndicatorSeries(name="ema", label=f"EMA({period})", values=out)]
        )
