"""Marketaux daily news sentiment as a feature — the sixth
connector-backed generator (`app.connectors.marketaux`), after
`fear_greed`, `fed_funds_rate`, `eth_gas_price`, `defillama_eth_tvl`, and
`btc_dominance`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical — no news-specific branch anywhere in this
generator, exactly as the task that added News required. This feature
has no idea `news_sentiment` is a *derived* aggregate (real articles live
in `app.models.news.NewsArticle`, browsable at `/news`; only the daily
mean sentiment is mirrored here) or that it may be revised as
late-discovered articles for an already-mirrored day arrive (see
`app.services.news_ingest._mirror_daily_aggregates`'s own docstring) —
`most_recent_value_at_or_before` just reads whatever is currently
stored, the same generic lookup every other feature already uses.
"""

from app.connectors.marketaux import MARKETAUX_SOURCE
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
class NewsSentimentFeature(FeatureGenerator):
    """The most recent known daily mean news sentiment at or before each
    candle.

    No warmup in the usual sense (the very first candle is looked up
    exactly like the last) — but `missing_values_expected=True` because a
    candle whose own timestamp predates whenever this platform first
    started polling Marketaux, or a calendar day with no tracked-symbol
    articles at all, legitimately has no value. `None` there, never a
    fabricated 0 or a forward-filled guess.
    """

    metadata = FeatureMetadata(
        name="news_sentiment",
        label="News Sentiment",
        description=(
            "The most recent known daily mean sentiment across real, "
            "tracked-symbol news articles (Marketaux), known at or before each "
            "candle's own timestamp. A derived aggregate — full article detail "
            "is browsable at /news. The same day's own value may change across "
            "two dataset builds if a late-discovered article for that day "
            "arrives after the first build. Null wherever no recorded value "
            "exists yet at or before that candle."
        ),
        category="sentiment",
        parameters=(),
        outputs=("news_sentiment",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("news", "marketaux_sentiment"),
        unit="",
        value_type="float",
        external_sources=(MARKETAUX_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`.

        `ctx.external_data` is pre-fetched, in full, by whichever service
        built this context — this method never queries anything itself,
        and never sees a point whose own `timestamp` is after the candle
        it's being asked about.
        """
        points = ctx.external_data.get(MARKETAUX_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="news_sentiment",
                        label="News Sentiment",
                        description="Most recent known daily mean news sentiment at or "
                        "before this candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
