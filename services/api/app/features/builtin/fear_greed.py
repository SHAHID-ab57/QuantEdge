"""The Fear & Greed Index as a feature — the first, and so far only,
connector-backed generator (`app.connectors.fear_greed`).

Read `ohlcv.py` first if this is the first connector-backed feature you're
looking at: everything about *registration* and *column shape* is
identical to an ordinary generator. The one genuinely new thing here is
`metadata.external_sources` and `ctx.external_data` — see
`app.features.base`'s own docstrings on `FeatureContext`/`FeatureMetadata`
for the full mechanism, and `tests/features/test_fear_greed_feature.py`
for the adversarial proof this never looks ahead.
"""

from app.connectors.fear_greed import FEAR_GREED_SOURCE
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
class FearGreedFeature(FeatureGenerator):
    """The most recent Fear & Greed Index value at or before each candle.

    No warmup in the usual sense (the very first candle is looked up
    exactly like the last) — but `missing_values_expected=True` because a
    candle whose own timestamp predates the index's earliest-ever
    recorded value (or the earliest point this platform has actually
    ingested) legitimately has no value at all, indefinitely, not just
    during a warmup window. `None` there, never a fabricated 0 or a
    forward-filled guess.
    """

    metadata = FeatureMetadata(
        name="fear_greed",
        label="Fear & Greed Index",
        description=(
            "The most recent Fear & Greed Index value (0-100: 'Extreme Fear' to "
            "'Extreme Greed') at or before each candle's own timestamp — never a "
            "value the source published after it. Null wherever no recorded value "
            "exists yet at or before that candle (the index's own history, or this "
            "platform's own ingested data, doesn't reach that far back)."
        ),
        category="sentiment",
        parameters=(),
        outputs=("fear_greed",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("fng", "sentiment"),
        unit="index (0-100)",
        value_type="float",
        external_sources=(FEAR_GREED_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`.

        `ctx.external_data` is pre-fetched, in full, by whichever service
        built this context (see `FeatureContext`'s own docstring) — this
        method never queries anything itself, and never sees a point
        whose own `timestamp` is after the candle it's being asked about.
        """
        points = ctx.external_data.get(FEAR_GREED_SOURCE, ())
        # Explicitly `list[FeatureValue]`, not the narrower `list[float |
        # None]` pyright would otherwise infer here: `list` is invariant,
        # so an un-annotated intermediate variable (unlike a list literal
        # inlined directly into `values=[...]`, which gets its element
        # type from the parameter it's passed to) fails that check below.
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="fear_greed",
                        label="Fear & Greed Index",
                        description="Most recent Fear & Greed Index value at or before this "
                        "candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
