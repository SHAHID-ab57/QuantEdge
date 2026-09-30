"""Reddit daily mean VADER sentiment as a feature
(REDDIT-SENTIMENT-CONNECTOR) — a connector-backed generator, same shape
as `news_sentiment.py`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical. This feature has no idea `reddit_sentiment` is
computed from VADER (a rule-based lexicon scorer, not Reddit's own data —
see `app.connectors.reddit.score_comment`) or that it is a *derived*
aggregate that may be revised as later comments for an already-mirrored
day arrive (see `app.services.reddit_ingest._mirror_daily_aggregates`'s
own docstring) — `most_recent_value_at_or_before` just reads whatever is
currently stored, the same generic lookup every other feature already
uses.
"""

from app.connectors.reddit import REDDIT_SENTIMENT_SOURCE
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
class RedditSentimentFeature(FeatureGenerator):
    """The most recent known daily mean VADER compound sentiment (across
    configured subreddits' comments) at or before each candle.

    No warmup in the usual sense — but `missing_values_expected=True`
    because a candle predating this platform's first Reddit sync, or a
    calendar day with no scoreable comments (all deleted/removed, or none
    at all), legitimately has no value.
    """

    metadata = FeatureMetadata(
        name="reddit_sentiment",
        label="Reddit Sentiment",
        description=(
            "The most recent known daily mean VADER compound sentiment "
            "([-1, 1], matching Marketaux's own sentiment_score scale) across "
            "configured cryptocurrency subreddits' comments, known at or "
            "before each candle's own timestamp. A derived aggregate — full "
            "comment detail is stored in reddit_comments. Null wherever no "
            "recorded value exists yet at or before that candle."
        ),
        category="sentiment",
        parameters=(),
        outputs=("reddit_sentiment",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("reddit_vader_sentiment",),
        unit="",
        value_type="float",
        external_sources=(REDDIT_SENTIMENT_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`.

        `ctx.external_data` is pre-fetched, in full, by whichever service
        built this context — this method never queries anything itself.
        """
        points = ctx.external_data.get(REDDIT_SENTIMENT_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="reddit_sentiment",
                        label="Reddit Sentiment",
                        description="Most recent known daily mean Reddit VADER sentiment "
                        "at or before this candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
