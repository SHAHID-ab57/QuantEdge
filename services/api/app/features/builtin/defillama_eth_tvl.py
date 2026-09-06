"""Ethereum chain TVL as a feature — the fourth connector-backed generator
(`app.connectors.defillama`), after `fear_greed.py`, `fed_funds_rate.py`,
and `eth_gas_price.py`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical. The one thing genuinely worth restating here:
this feature has no idea `eth_tvl` is a *revisable* source — an
already-ingested value may have been silently overwritten in place by a
later sync tick (see `app.services.external_data_ingest`'s own `updated`
handling and `ConnectorMetadata.revisable`). `most_recent_value_at_or_before`
just reads whatever is currently stored for a given timestamp; a revision
changes what that read returns for the *same* timestamp between two
dataset builds, which is expected and correct here, not a bug — the whole
point of `revisable=True` is that "the value DefiLlama reports for date
X" is itself allowed to change over time.
"""

from app.connectors.defillama import DEFILLAMA_SOURCE
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
class DefiLlamaEthTvlFeature(FeatureGenerator):
    """The most recent known Ethereum chain TVL at or before each candle.

    No warmup in the usual sense (the very first candle is looked up
    exactly like the last) — but `missing_values_expected=True` because a
    candle whose own timestamp predates the earliest value this platform
    has actually ingested (DefiLlama's own history goes back to 2017, so
    in practice this only bites a candle before this source was ever
    backfilled) legitimately has no value at all. `None` there, never a
    fabricated 0 or a forward-filled guess.
    """

    metadata = FeatureMetadata(
        name="eth_tvl",
        label="Ethereum Chain TVL",
        description=(
            "The most recent known total value locked in DeFi on Ethereum "
            "(DefiLlama's v2/historicalChainTvl, in USD) at or before each "
            "candle's own timestamp. DefiLlama does not guarantee a published "
            "figure is final, so the same historical timestamp may report a "
            "different value across two dataset builds if DefiLlama has since "
            "revised it — see app.connectors.defillama's own module docstring. "
            "Null wherever no recorded value exists yet at or before that "
            "candle."
        ),
        category="on-chain",
        parameters=(),
        outputs=("eth_tvl",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("tvl", "defillama_tvl", "chain_tvl"),
        unit="usd",
        value_type="float",
        external_sources=(DEFILLAMA_SOURCE,),
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
        points = ctx.external_data.get(DEFILLAMA_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="eth_tvl",
                        label="Ethereum Chain TVL",
                        description="Most recent known Ethereum chain TVL (USD) at or before "
                        "this candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
