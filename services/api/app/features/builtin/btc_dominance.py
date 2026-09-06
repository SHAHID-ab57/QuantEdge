"""Bitcoin dominance as a feature — the fifth connector-backed generator
(`app.connectors.coingecko`), after `fear_greed.py`, `fed_funds_rate.py`,
`eth_gas_price.py`, and `defillama_eth_tvl.py`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical. The one thing genuinely worth restating here:
this is the first feature in the new `"market"` category — a market-wide
capital-rotation signal, distinct from `"on-chain"` (a single chain's own
network state, e.g. gas price or TVL), `"macro"` (policy backdrop), or
`"sentiment"` (an aggregated mood index) — since BTC dominance describes
capital allocation *across* the whole cryptocurrency market, not any one
chain or asset's own state.
"""

from app.connectors.coingecko import COINGECKO_SOURCE
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
class BtcDominanceFeature(FeatureGenerator):
    """The most recent known BTC dominance at or before each candle.

    No warmup in the usual sense (the very first candle is looked up
    exactly like the last) — but `missing_values_expected=True` because a
    candle whose own timestamp predates whenever this platform first
    started polling CoinGecko (this source has no historical query
    capability at all, mirroring `eth_gas_price`) legitimately has no
    value at all. `None` there, never a fabricated 0 or a forward-filled
    guess.
    """

    metadata = FeatureMetadata(
        name="btc_dominance",
        label="Bitcoin Dominance",
        description=(
            "The most recent known Bitcoin dominance (CoinGecko's "
            "market_cap_percentage.btc, a 0-100 percentage of total "
            "cryptocurrency market cap) known at or before each candle's own "
            "timestamp. This source has no historical query capability, so "
            "null wherever no recorded value exists yet at or before that "
            "candle, including for any candle before this platform started "
            "polling it, not just a brief warmup window."
        ),
        category="market",
        parameters=(),
        outputs=("btc_dominance",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("btc_dom", "dominance"),
        unit="percent",
        value_type="float",
        external_sources=(COINGECKO_SOURCE,),
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
        points = ctx.external_data.get(COINGECKO_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="btc_dominance",
                        label="Bitcoin Dominance",
                        description="Most recent known BTC dominance (%) at or before this candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
