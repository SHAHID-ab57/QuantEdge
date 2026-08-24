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
    IndicatorSeries,
    SeriesSpec,
)
from app.indicators.params import ParameterSpec
from app.indicators.registry import register

PRICE_SOURCES = ("open", "high", "low", "close")


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
            ParameterSpec(
                name="period",
                type="int",
                label="Period",
                description="Number of candles averaged into each point.",
                default=20,
                minimum=1,
                maximum=1000,
            ),
            ParameterSpec(
                name="source",
                type="string",
                label="Source",
                description="Which price of each candle to average.",
                default="close",
                choices=PRICE_SOURCES,
            ),
        ),
        outputs=(
            SeriesSpec(
                name="sma",
                label="SMA",
                description="The moving average itself.",
            ),
        ),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        """A full window is needed before the first value."""
        return int(params["period"])

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Compute the rolling mean using an O(n) running sum."""
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

        return IndicatorOutput(
            series=[IndicatorSeries(name="sma", label=f"SMA({period})", values=out)]
        )
