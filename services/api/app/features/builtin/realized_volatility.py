"""Realized volatility — the population standard deviation of hourly log
returns over a trailing window, the one measurement missing from the
platform's fixed feature set (MODEL-QUALITY-T2).

**Why this exists.** `docs/research/TARGET_REDEFINITION_ASSESSMENT.md`
confirmed real, strong volatility clustering on this platform's own data
(autocorrelation of squared/absolute hourly log returns persists past lag
100, Ljung-Box Q(20) ~= 1,138 against a ~45 critical value) and then built
`volatility_regime` — a target asking whether realized volatility over the
next window will exceed realized volatility over the trailing window — but
tested it against `ohlc` + `volume_log` + `sma(20)`, none of which
*directly* measures volatility: price levels, log-volume, and a moving
average of price can only proxy it indirectly. The primary comparison came
back flat (ROC-AUC 0.49-0.55, permutation importance under 0.03
everywhere) — a plausible consequence of that gap, not yet a settled
answer, since the diagnostic never got the chance to be tested with the
right tool. This feature is that tool: the exact same trailing-window
realized-volatility computation `volatility_regime`'s own target already
uses on the *forward* side, now available as an input on the *backward*
side too.

Deliberately population stdev of log returns, not ATR: matching the
target's own definition exactly means a model comparing "trailing vol vs.
forward vol" is comparing two numbers computed the same way, not two
different volatility conventions that happen to correlate.
"""

import math
from statistics import pstdev

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
    FeatureValue,
    ParameterSpec,
)
from app.features.registry import register

WINDOW_PARAMETER = ParameterSpec(
    name="window",
    type="int",
    label="Volatility Window (hours)",
    description="Hours of trailing hourly log returns the standard deviation is computed over.",
    default=24,
    minimum=2,
    maximum=500,
)


@register
class RealizedVolatilityFeature(FeatureGenerator):
    """Population standard deviation of the trailing `window` hourly log
    returns, ending at (and including the return into) each candle.

    Undefined for a candle's first `window` positions — there are not yet
    `window` real returns behind it — mirroring `sma`'s own leading-`None`
    warmup convention exactly.
    """

    metadata = FeatureMetadata(
        name="realized_volatility",
        label="Realized Volatility",
        description=(
            "Population standard deviation of hourly log returns over the trailing `window` hours."
        ),
        category="volatility",
        parameters=(WINDOW_PARAMETER,),
        outputs=("realized_volatility_{window}",),
        version="1.0.0",
        complexity="O(n * window) — one trailing-window stdev per candle.",
        warmup_description="`window` candles; undefined until `window` real returns exist.",
        unit="stdev of log return",
        value_type="float",
        is_deterministic=True,
        missing_values_expected=False,
    )

    def warmup(self, params: dict[str, object]) -> int:
        return int(params["window"])  # type: ignore[arg-type]

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        window = ctx.int_param("window")
        candles = ctx.candles
        n = len(candles)
        name = f"realized_volatility_{window}"

        log_returns: list[FeatureValue] = [None]
        for index in range(1, n):
            previous_close = candles[index - 1].close
            if previous_close <= 0:
                log_returns.append(None)
            else:
                log_returns.append(math.log(candles[index].close / previous_close))

        values: list[FeatureValue] = []
        for index in range(n):
            if index < window:
                values.append(None)
                continue
            trailing = log_returns[index - window + 1 : index + 1]
            if any(r is None for r in trailing):
                values.append(None)
                continue
            values.append(pstdev(trailing))  # type: ignore[arg-type]

        column = FeatureColumn(
            name=name,
            label=f"Realized Volatility ({window}h)",
            description=(
                f"Population standard deviation of hourly log returns over the "
                f"trailing {window} hours."
            ),
            dtype="float",
        )
        return FeatureOutput(series=[FeatureSeries(column=column, values=values)])
