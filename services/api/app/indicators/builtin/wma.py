"""Weighted Moving Average — a windowed indicator with linear weighting.

Sits between SMA and EMA on the "how much does the newest candle count"
spectrum: unlike SMA, recent candles count more; unlike EMA, the weighting
is a fixed linear ramp recomputed per window rather than a recursive decay
carried across the whole series. Added as the third member of the Trend
Indicator Package alongside SMA and EMA, following the exact workflow
documented in ``ARCHITECTURE.md`` § "Adding a new indicator" — no change
to the engine, registry, API, or frontend was needed to add it.
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
class WeightedMovingAverage(Indicator):
    """Mean of the last ``period`` values, weighted linearly toward the newest."""

    metadata = IndicatorMetadata(
        name="wma",
        label="Weighted Moving Average",
        description=(
            "A moving average that weights each candle in the window linearly "
            "by recency — the newest candle counts most, the oldest counts "
            "least — so it reacts faster than an SMA of the same period "
            "without an EMA's unbounded recursive memory."
        ),
        category="trend",
        parameters=(
            period_parameter(description="Number of candles in the weighted window."),
            source_parameter(description="Which price of each candle to average."),
        ),
        outputs=(
            SeriesSpec(
                name="wma",
                label="WMA",
                description="The linearly-weighted moving average itself.",
            ),
        ),
        version="1.0.0",
        author="Eth AI Platform",
        complexity="O(n) — one incremental pass over the candle range after an O(period) seed.",
        warmup_description="Equal to the period parameter.",
        aliases=("Weighted MA", "Linear Weighted Moving Average", "LWMA"),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        """A full window is needed before the first weighted value."""
        return period_warmup(params)

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Compute the linearly-weighted rolling mean in a single O(n) pass.

        Weight ``i`` (1-indexed from the oldest candle in the window) is
        ``i``, so the newest candle in a period-N window carries weight N
        and the oldest carries weight 1.

        A naive re-implementation recomputes the weighted sum from
        scratch for every window (O(period) per point, O(n * period)
        overall) because, unlike SMA's plain sum, a weighted sum cannot
        obviously be updated by subtracting one old term — every
        remaining term's *weight* also shifts by one when the window
        slides. It turns out it still can, via the identity this
        implementation uses::

            weighted(t+1) = weighted(t) + N * x(t+1) - total(t)
            total(t+1)    = total(t) - x(t+1-N) + x(t+1)

        where ``total`` is the window's plain (unweighted) sum — itself
        already tracked for exactly this purpose, at no extra asymptotic
        cost, the same running sum SMA uses. This turns the per-point cost
        from O(period) into O(1), making the indicator truly O(n) overall
        (one O(period) seed for the first window, then O(1) per remaining
        point) rather than O(n * period) — the same complexity class as
        SMA and EMA. Verified against an independent, from-scratch
        weighted-average computation in
        ``test_matches_an_independent_reference_implementation_on_a_large_dataset``,
        so the optimization can never silently change the result it
        produces.
        """
        period = ctx.int_param("period")
        values = ctx.source_values()
        weight_sum = period * (period + 1) / 2.0

        out: list[float | None] = [None] * len(values)

        window_total = sum(values[:period])
        weighted_total = sum(
            (position + 1) * value for position, value in enumerate(values[:period])
        )
        out[period - 1] = weighted_total / weight_sum

        for index in range(period, len(values)):
            new_value = values[index]
            old_value = values[index - period]
            weighted_total = weighted_total + period * new_value - window_total
            window_total = window_total - old_value + new_value
            out[index] = weighted_total / weight_sum

        return single_series_output("wma", f"WMA({period})", out)
