"""Simple Moving Average — the reference windowed indicator.

The simplest possible implementation of the contract: one parameter, one
output series, a fixed warmup. Read this first when adding a new indicator.
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
    PRICE_SOURCES,
    period_parameter,
    period_warmup,
    single_series_output,
    source_parameter,
)
from app.indicators.registry import register

__all__ = ["PRICE_SOURCES", "SimpleMovingAverage"]


@register
class SimpleMovingAverage(Indicator):
    """Unweighted mean of the last ``period`` values of the chosen source."""

    metadata = IndicatorMetadata(
        name="sma",
        label="Simple Moving Average",
        description=(
            "The unweighted mean of the last N values. The baseline trend "
            "indicator: every point weighs equally, so it is smooth but lags "
            "price by roughly half the period."
        ),
        category="trend",
        parameters=(
            period_parameter(description="Number of candles averaged into each point."),
            source_parameter(description="Which price of each candle to average."),
        ),
        outputs=(
            SeriesSpec(
                name="sma",
                label="SMA",
                description="The moving average itself.",
            ),
        ),
        version="1.0.0",
        author="Eth AI Platform",
        complexity="O(n) — one running-sum pass over the candle range.",
        warmup_description="Equal to the period parameter.",
        aliases=("MA", "Moving Average", "Simple MA"),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        """A full window is needed before the first value."""
        return period_warmup(params)

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Compute the rolling mean using an O(n) running sum.

        Deterministic and numerically stable for any realistic candle
        count: the running sum only ever adds and removes values already
        present in the series (no repeated re-summation of the whole
        window), so there is no accumulation of rounding error beyond the
        one unavoidable float addition/subtraction per step — the same
        floating-point behavior Python's own ``sum()`` would produce, just
        without redoing O(period) work at every point.
        """
        period = ctx.int_param("period")
        values = ctx.source_values()

        out: list[float | None] = [None] * len(values)
        window_sum = 0.0
        for index, value in enumerate(values):
            window_sum += value
            if index >= period:
                window_sum -= values[index - period]
            if index >= period - 1:
                out[index] = window_sum / period

        return single_series_output("sma", f"SMA({period})", out)
