"""Shared building blocks for windowed moving-average-style indicators.

SMA, EMA, and WMA independently grew the identical ``period``/``source``
parameter declarations, the identical "warmup equals the period" rule, and
the identical "wrap one computed series as the output" shape. Extracted
here once three indicators had copied that code three times, so a fourth
(Hull MA, VWMA, KAMA, ...) doesn't have to copy it a fourth time — see
``ARCHITECTURE.md`` § "Shared Moving-Average Utilities".

Nothing here is mandatory: an indicator that doesn't fit this shape (RSI's
warmup is the period *plus one*, for instance) simply doesn't call these
and declares its own — these are conveniences for the common case, not a
second base class every indicator must extend.
"""

from collections.abc import Mapping
from typing import Any

from app.indicators.base import IndicatorOutput, IndicatorSeries
from app.indicators.params import ParameterSpec

#: The four price fields every ``OHLCVPoint`` carries; the ``source``
#: parameter is always constrained to exactly these.
PRICE_SOURCES = ("open", "high", "low", "close")


def period_parameter(
    *,
    description: str,
    default: int = 20,
    minimum: int = 1,
    maximum: int = 1000,
) -> ParameterSpec:
    """The ``period`` parameter almost every windowed indicator declares.

    ``description`` is required rather than defaulted: it is the one part
    of this parameter that genuinely differs per indicator (what the
    window means for *this* calculation), so callers must say it rather
    than inherit generic wording.
    """
    return ParameterSpec(
        name="period",
        type="int",
        label="Period",
        description=description,
        default=default,
        minimum=minimum,
        maximum=maximum,
    )


def source_parameter(
    *,
    description: str = "Which price of each candle to average.",
    default: str = "close",
) -> ParameterSpec:
    """The ``source`` parameter every price-based indicator declares."""
    return ParameterSpec(
        name="source",
        type="string",
        label="Source",
        description=description,
        default=default,
        choices=PRICE_SOURCES,
    )


def period_warmup(params: Mapping[str, Any]) -> int:
    """Warmup equal to the ``period`` parameter — the common case for a windowed average."""
    return int(params["period"])


def single_series_output(name: str, label: str, values: list[float | None]) -> IndicatorOutput:
    """Wrap one computed series as the ``IndicatorOutput`` most indicators return.

    Most indicators built on this engine produce exactly one output
    series; a multi-series indicator (MACD, Bollinger Bands) constructs
    ``IndicatorOutput`` directly instead, since this helper's whole point
    is the single-series shortcut.
    """
    return IndicatorOutput(series=[IndicatorSeries(name=name, label=label, values=values)])
