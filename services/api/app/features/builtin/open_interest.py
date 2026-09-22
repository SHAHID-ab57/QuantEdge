"""ETHUSD's perpetual open interest as a feature (`app.connectors.delta_market_data`).

Registration, column shape and the as-of lookup are identical to the other
connector-backed features (`fear_greed.py` and the rest). What is specific here is
**which value counts as knowable at a candle** (the M4-E3-T3 Step 1 finding, in full
in `app.connectors.delta_market_data`): open interest is stored as the OI candle's
*open* stamped at the candle's open time (OI at the start of the hour), so a candle at
or after that time may use it; the candle's close is not known until an hour later and
is never used. **ETHUSD only**: the lookup is global (`symbol=None`), so this feature
must not build a dataset for another market.
"""

from app.connectors.delta_market_data import OPEN_INTEREST_SOURCE
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
class OpenInterestFeature(FeatureGenerator):
    """The most recent ETHUSD open interest (ETH) sampled at or before each candle.

    A raw *level*, not a change: it is non-stationary (it trends with the market's size
    over the years), which the M4-E3-T3 assessment treats and discloses explicitly.
    Null before the earliest ingested value (2024-02-06)."""

    metadata = FeatureMetadata(
        name="open_interest",
        label="ETHUSD Open Interest",
        description=(
            "The most recent ETHUSD perpetual open interest, in ETH, sampled at or before "
            "each candle's own timestamp (the value at the START of an hour, never the "
            "hour's close). A raw level, not a change. ETHUSD only. Null before the first "
            "ingested value."
        ),
        category="derivatives",
        parameters=(),
        outputs=("open_interest",),
        version="1.0.0",
        complexity="O(log n) per candle: one bisect search over the pre-fetched source series.",
        warmup_description="None: the first candle is looked up exactly like the last.",
        aliases=("oi", "ethusd_oi"),
        unit="ETH",
        value_type="float",
        external_sources=(OPEN_INTEREST_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`."""
        points = ctx.external_data.get(OPEN_INTEREST_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="open_interest",
                        label="ETHUSD Open Interest",
                        description=(
                            "Most recent ETHUSD open interest (ETH) at or before this candle."
                        ),
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
