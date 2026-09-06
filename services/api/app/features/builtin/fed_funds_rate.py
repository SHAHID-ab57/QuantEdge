"""The Federal Funds Rate as a feature — the second connector-backed
generator (`app.connectors.fred`), after `fear_greed.py`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical. The one thing genuinely worth restating here:
this feature never re-derives or corrects for FRED's own publication lag
— that correctness already lives entirely in `app.connectors.fred`'s own
choice of `RawDataPoint.timestamp` (FRED's `realtime_start`, never
`date`; see that module's own docstring). `most_recent_value_at_or_before`
just does the same generic bisect search over whatever timestamp it was
given — it has no idea this source happens to publish with a lag, and it
doesn't need to.
"""

from app.connectors.fred import FRED_SOURCE
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
class FedFundsRateFeature(FeatureGenerator):
    """The most recent (by real publication date) federal funds rate at or
    before each candle.

    No warmup in the usual sense (the very first candle is looked up
    exactly like the last) — but `missing_values_expected=True` because a
    candle whose own timestamp predates the earliest value this platform
    has actually ingested (FEDFUNDS's own history goes back to July
    1954, so in practice this only bites a candle before this source was
    ever backfilled) legitimately has no value at all. `None` there,
    never a fabricated 0 or a forward-filled guess.
    """

    metadata = FeatureMetadata(
        name="fed_funds_rate",
        label="Federal Funds Rate",
        description=(
            "The most recent effective federal funds rate (FRED series FEDFUNDS, "
            "monthly) known as of each candle's own timestamp — by its real "
            "publication date, never the calendar month it describes, so no "
            "candle ever sees a rate before it was actually knowable. Null "
            "wherever no recorded value exists yet at or before that candle."
        ),
        category="macro",
        parameters=(),
        outputs=("fed_funds_rate",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("fedfunds", "interest_rate"),
        unit="percent",
        value_type="float",
        external_sources=(FRED_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`.

        `ctx.external_data` is pre-fetched, in full, by whichever service
        built this context — this method never queries anything itself,
        and never sees a point whose own `timestamp` (already the
        publication date, not the reference month — see this module's own
        docstring) is after the candle it's being asked about.
        """
        points = ctx.external_data.get(FRED_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="fed_funds_rate",
                        label="Federal Funds Rate",
                        description="Most recent federal funds rate known at or before this "
                        "candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
