"""`log1p(volume)` — a single derived column, for a feature set that wants
volume's information without its raw, ever-growing absolute scale.

**Why this exists** (RETRAIN-WITH-MINIMUM-WINDOW,
`docs/research/RETRAIN_WINDOW_ANALYSIS.md`): unlike price, which is close to
range-bound over the timescales a rolling training window spans, `volume`'s
real absolute level trends upward over calendar time with genuine market
growth — a fixed historical mean/std fit on it goes stale in a way no
practical window width or retraining cadence can fully prevent. Measured
directly on the real stored ETHUSD history: raw `volume`'s z-score against
its own best-chosen training window still reaches the high tens (p99 in the
teens to 40s, worst case over 60, across every window/cadence combination
checked) — nowhere close to safe. `log1p(volume)` — chosen over a bare
`log(volume)` only so a candle with zero volume has a defined value (`log(0)`
is undefined; `log1p(0) = 0`) — measured under the identical methodology,
keeps its own z-score's 99th percentile at 3-4 and its worst case under 10
across the same grid: a percentage change in volume becomes a roughly
additive change in this column, which a window many months wide can actually
represent, the same way it already represents price.

This does **not** replace `volume` inside the bundled `ohlcv` feature (see
`ohlc.py`'s own docstring for why) — a feature set that wants this instead
of raw volume requests `ohlc` + `volume_log`, not `ohlcv` + `volume_log`
(which would carry both).
"""

import math

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
)
from app.features.registry import register


@register
class VolumeLogFeature(FeatureGenerator):
    """`log1p` of each candle's own base-asset volume."""

    metadata = FeatureMetadata(
        name="volume_log",
        label="Volume (log)",
        description=(
            "log1p(volume) — a candle's base-asset volume, log-transformed so a "
            "percentage change in real trading activity becomes a roughly additive "
            "change in this column, rather than a raw value whose absolute scale "
            "trends upward over calendar time with genuine market growth. log1p, "
            "not a bare log, so a candle with zero volume (a real, if rare, case "
            "in a thin market) has a defined value (0) rather than an undefined one."
        ),
        category="raw",
        parameters=(),
        outputs=("volume_log",),
        version="1.0.0",
        complexity="O(n) — one pass, one log per candle.",
        warmup_description="None; defined from the first candle.",
        aliases=("log_volume",),
        unit="log(base-asset volume + 1)",
        value_type="float",
        is_deterministic=True,
        missing_values_expected=False,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="volume_log",
                        label="Volume (log)",
                        description="log1p of the candle's own base-asset volume.",
                        dtype="float",
                    ),
                    values=[math.log1p(candle.volume) for candle in ctx.candles],
                )
            ]
        )
