"""Volatility-regime classification — will realized volatility expand or
contract, exploiting the volatility clustering this platform's own real
ETHUSD/1h history was confirmed to show.

Investigated for MODEL-QUALITY-T1 alongside `triple_barrier.py` as a
candidate replacement for `next_direction`'s failed binary-direction
target (see that module's own docstring for the full research context).
Unlike direction, which five independent checks across this thread found
no better than chance, volatility clustering is not assumed from general
market-structure literature — `docs/research/TARGET_REDEFINITION_ASSESSMENT.md`
measured it directly on this platform's own stored data before this
target was written: the autocorrelation of squared/absolute hourly log
returns is strongly positive and persists for 100+ lags (Ljung-Box
Q(20) ~= 1,138 against a ~45 critical value), while the autocorrelation of
the raw returns themselves is flat — the textbook volatility-clustering
signature, real on this data, not merely plausible in general.
"""

import math
from statistics import pstdev

from app.ml_datasets.base import (
    FeatureValue,
    ParameterSpec,
    TargetColumn,
    TargetContext,
    TargetGenerator,
    TargetMetadata,
    TargetOutput,
    TargetSeries,
)
from app.ml_datasets.registry import register

WINDOW_HOURS_PARAMETER = ParameterSpec(
    name="window_hours",
    type="int",
    label="Volatility Window (hours)",
    description=(
        "Hours over which realized volatility is measured, both trailing "
        "(already known at this row) and forward (what is being predicted)."
    ),
    default=24,
    minimum=2,
    maximum=500,
)


@register
class VolatilityRegime(TargetGenerator):
    """Whether realized volatility over the next `window_hours` is higher
    ('expand') or lower-or-equal ('contract') than realized volatility over
    the trailing `window_hours`, both measured as the population standard
    deviation of hourly log returns.

    A binary framing chosen deliberately over raw regression: it fits the
    same three-classifier comparison (`logistic_regression`,
    `random_forest`, `gradient_boosting`) every other target in this
    research thread was checked against, rather than requiring a fourth,
    regression-only model class to be added just for this one target. It
    also operationalizes volatility clustering directly — "will the next
    window look more or less turbulent than the one just observed" is
    exactly the question the ACF diagnostic answered "yes, persistently"
    to.
    """

    metadata = TargetMetadata(
        name="volatility_regime",
        label="Volatility Regime",
        description=(
            "Whether realized volatility over the next window_hours is "
            "higher ('expand') or lower-or-equal ('contract') than realized "
            "volatility over the trailing window_hours."
        ),
        category="volatility",
        parameters=(WINDOW_HOURS_PARAMETER,),
        outputs=("volatility_regime_{window_hours}",),
        value_type="categorical",
        is_deterministic=True,
    )

    def horizon(self, params: dict[str, object]) -> int:
        return int(params["window_hours"])  # type: ignore[arg-type]

    def generate(self, ctx: TargetContext) -> TargetOutput:
        window = ctx.int_param("window_hours")
        candles = ctx.candles
        n = len(candles)
        name = f"volatility_regime_{window}"

        log_returns: list[float | None] = [None]
        for index in range(1, n):
            previous_close = candles[index - 1].close
            if previous_close <= 0:
                log_returns.append(None)
            else:
                log_returns.append(math.log(candles[index].close / previous_close))

        values: list[FeatureValue] = []
        boundary = n - window
        for index in range(n):
            if index < window or index >= boundary:
                values.append(None)
                continue
            trailing = log_returns[index - window + 1 : index + 1]
            forward = log_returns[index + 1 : index + 1 + window]
            if any(r is None for r in trailing) or any(r is None for r in forward):
                values.append(None)
                continue
            trailing_vol = pstdev(trailing)  # type: ignore[arg-type]
            forward_vol = pstdev(forward)  # type: ignore[arg-type]
            values.append("expand" if forward_vol > trailing_vol else "contract")

        column = TargetColumn(
            name=name,
            label=f"Volatility Regime ({window}h)",
            description=(
                f"Whether realized volatility over the next {window} hours "
                f"exceeds realized volatility over the trailing {window} hours."
            ),
            dtype="categorical",
        )
        return TargetOutput(series=[TargetSeries(column=column, values=values)])
