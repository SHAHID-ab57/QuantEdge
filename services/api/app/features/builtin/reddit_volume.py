"""Reddit daily comment volume as a feature (REDDIT-SENTIMENT-CONNECTOR) —
a connector-backed generator, same shape as `news_sentiment.py`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical — no Reddit-specific branch anywhere in this
generator. This feature has no idea `reddit_volume` is a *derived*
aggregate (real comments live in `app.models.reddit.RedditComment`; only
the daily count is mirrored here) — `most_recent_value_at_or_before` just
reads whatever is currently stored, the same generic lookup every other
feature already uses.
"""

from app.connectors.reddit import REDDIT_VOLUME_SOURCE
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
class RedditVolumeFeature(FeatureGenerator):
    """The most recent known daily Reddit comment count at or before each
    candle, across the configured subreddits (`reddit_subreddits`).

    No warmup in the usual sense — but `missing_values_expected=True`
    because a candle predating this platform's first Reddit sync, or a
    calendar day with zero comments, legitimately has no value. `None`
    there, never a fabricated 0 or a forward-filled guess (a real zero-
    comment day and "not tracked yet" must stay distinguishable).
    """

    metadata = FeatureMetadata(
        name="reddit_volume",
        label="Reddit Comment Volume",
        description=(
            "The most recent known daily comment count across configured "
            "cryptocurrency subreddits (via Arctic Shift), known at or before "
            "each candle's own timestamp. A derived aggregate — full comment "
            "detail is stored in reddit_comments. Null wherever no recorded "
            "value exists yet at or before that candle (distinct from a real "
            "zero-comment day, which is recorded as 0.0)."
        ),
        category="sentiment",
        parameters=(),
        outputs=("reddit_volume",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("reddit", "reddit_comment_count"),
        unit="comments/day",
        value_type="float",
        external_sources=(REDDIT_VOLUME_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`.

        `ctx.external_data` is pre-fetched, in full, by whichever service
        built this context — this method never queries anything itself.
        """
        points = ctx.external_data.get(REDDIT_VOLUME_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="reddit_volume",
                        label="Reddit Comment Volume",
                        description="Most recent known daily Reddit comment count at or "
                        "before this candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
