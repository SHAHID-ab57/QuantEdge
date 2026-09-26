"""ETHUSD's perpetual funding rate as a feature (`app.connectors.delta_market_data`).

Registration, column shape and the as-of lookup are identical to the other
connector-backed features (`fear_greed.py` and the rest). What is specific here is
**which value counts as knowable at a candle** (the M4-E3-T3 Step 1 finding, in full
in `app.connectors.delta_market_data`): the funding rate is a step function set at each
funding time (00:00, 08:00, 16:00 UTC) and stored stamped with that time, so a candle
at or after it may use it; nothing later is ever visible. **ETHUSD only**: the lookup is
global (`symbol=None`), so this feature must not build a dataset for another market.
"""

from app.connectors.delta_market_data import FUNDING_SOURCE
from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
    FeatureValue,
    most_recent_value_at_or_before,
)
from app.features.registry import register


@register
class FundingRateFeature(FeatureGenerator):
    """The most recent ETHUSD funding rate set at or before each candle.

    Null before the earliest ingested value (Delta's history starts 2024-02-05), never a
    fabricated 0 or a guess. Delta's rate is floored at 0.01% per interval, so it sits
    on that floor about 69.5% of the time: a near-constant feature by construction."""

    metadata = FeatureMetadata(
        name="funding_rate",
        label="ETHUSD Funding Rate",
        description=(
            "The most recent ETHUSD perpetual funding rate (a fraction per 8-hour interval, "
            "0.0001 = 0.01%) set at or before each candle's own timestamp, never one set "
            "after it. A step function: the value at a funding time is knowable from that "
            "moment and never revised. ETHUSD only. Null before the first ingested value."
        ),
        category="derivatives",
        parameters=(),
        outputs=("funding_rate",),
        version="1.0.0",
        complexity="O(log n) per candle: one bisect search over the pre-fetched source series.",
        warmup_description="None: the first candle is looked up exactly like the last.",
        aliases=("funding", "ethusd_funding"),
        unit="fraction per 8h",
        value_type="float",
        external_sources=(FUNDING_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`."""
        points = ctx.external_data.get(FUNDING_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="funding_rate",
                        label="ETHUSD Funding Rate",
                        description=(
                            "Most recent ETHUSD funding rate (fraction per 8h) set at or before "
                            "this candle."
                        ),
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
