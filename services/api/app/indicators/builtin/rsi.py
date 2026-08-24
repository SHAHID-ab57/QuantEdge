"""Relative Strength Index — the reference *multi-stage, bounded* indicator.

The third distinct shape in the contract: RSI derives an intermediate
series (period-over-period gains and losses) before producing its output,
its warmup is one candle longer than its period (the first candle yields no
change), and its range is bounded to 0-100. Anyone adding an oscillator
should follow this file.
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
from app.indicators.builtin.common import period_parameter, single_series_output, source_parameter
from app.indicators.registry import register

#: RSI is undefined when there is no downside at all over the window; the
#: conventional rendering of "infinitely strong" is a flat 100.
_NO_LOSSES_RSI = 100.0


@register
class RelativeStrengthIndex(Indicator):
    """Wilder's RSI: smoothed average gain versus average loss, scaled 0-100."""

    metadata = IndicatorMetadata(
        name="rsi",
        label="Relative Strength Index",
        description=(
            "A 0-100 momentum oscillator comparing the size of recent gains to "
            "recent losses, using Wilder's smoothing. Conventionally read as "
            "overbought above 70 and oversold below 30 — thresholds that are a "
            "convention, not a signal this platform generates."
        ),
        category="momentum",
        parameters=(
            period_parameter(
                description="Look-back for the smoothed gain/loss averages.",
                default=14,
                minimum=2,
            ),
            source_parameter(description="Which price of each candle to measure changes on."),
        ),
        outputs=(
            SeriesSpec(
                name="rsi",
                label="RSI",
                description="The oscillator value, bounded to 0-100.",
            ),
        ),
        version="1.0.0",
        author="Eth AI Platform",
        complexity="O(n) — one Wilder-smoothing pass over the candle range.",
        warmup_description=(
            "One more than the period parameter — its first candle produces no change to measure."
        ),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        """One more than the period: the first candle produces no change."""
        return int(params["period"]) + 1

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Seed with a simple mean of the first window, then smooth Wilder-style."""
        period = ctx.int_param("period")
        values = ctx.source_values()

        out: list[float | None] = [None] * len(values)
        gains: list[float] = [0.0] * len(values)
        losses: list[float] = [0.0] * len(values)
        for index in range(1, len(values)):
            change = values[index] - values[index - 1]
            gains[index] = max(change, 0.0)
            losses[index] = max(-change, 0.0)

        # Changes live at indices 1..period for the first window, so the
        # first RSI value lands at index `period`.
        avg_gain = sum(gains[1 : period + 1]) / period
        avg_loss = sum(losses[1 : period + 1]) / period
        out[period] = _rsi(avg_gain, avg_loss)

        for index in range(period + 1, len(values)):
            avg_gain = (avg_gain * (period - 1) + gains[index]) / period
            avg_loss = (avg_loss * (period - 1) + losses[index]) / period
            out[index] = _rsi(avg_gain, avg_loss)

        return single_series_output("rsi", f"RSI({period})", out)


def _rsi(avg_gain: float, avg_loss: float) -> float:
    """Convert smoothed gain/loss averages into the 0-100 oscillator value."""
    if avg_loss == 0.0:
        return _NO_LOSSES_RSI
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
