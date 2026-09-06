"""Ethereum gas price as a feature — the third connector-backed generator
(`app.connectors.etherscan`), after `fear_greed.py` and `fed_funds_rate.py`.

Read `fear_greed.py` first if this is not the first connector-backed
feature you're looking at: registration, column shape, and the lookup
itself are all identical. Nothing here special-cases the fact that
`eth_gas_price` (the source) has no historical backfill capability —
`most_recent_value_at_or_before` just does the same generic bisect search
over whatever points happen to be stored; a candle from before this
platform started polling Etherscan legitimately has none yet, the same
"missing, not failed" outcome a candle predating Fear & Greed's own
ingestion already gets.
"""

from app.connectors.etherscan import ETHERSCAN_SOURCE
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
class EthGasPriceFeature(FeatureGenerator):
    """The most recent (by observation time) Ethereum gas price at or
    before each candle.

    No warmup in the usual sense (the very first candle is looked up
    exactly like the last) — but `missing_values_expected=True`, and more
    likely to actually occur here than for `fear_greed`/`fed_funds_rate`:
    this source has no historical backfill at all, so every candle
    before this platform first polled Etherscan has no value, for as long
    as that gap lasts. `None` there, never a fabricated 0 or a
    forward-filled guess.
    """

    metadata = FeatureMetadata(
        name="eth_gas_price",
        label="Ethereum Gas Price",
        description=(
            "The most recent known Ethereum gas price (Etherscan's Gas Oracle "
            "ProposeGasPrice, in Gwei) at or before each candle's own timestamp. "
            "This source has no historical query capability — null wherever no "
            "recorded value exists yet at or before that candle, including for "
            "any candle before this platform started polling it, not just a "
            "brief warmup window."
        ),
        category="on-chain",
        parameters=(),
        outputs=("eth_gas_price",),
        version="1.0.0",
        complexity="O(log n) per candle — one bisect search over the pre-fetched source series.",
        warmup_description="None — the first candle is looked up exactly like the last.",
        aliases=("gas_price", "gwei"),
        unit="gwei",
        value_type="float",
        external_sources=(ETHERSCAN_SOURCE,),
        is_deterministic=True,
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Look up the most recent value at or before each candle's `open_time`.

        `ctx.external_data` is pre-fetched, in full, by whichever service
        built this context — this method never queries anything itself,
        and never sees a point whose own `timestamp` (the moment it was
        actually observed — see `app.connectors.etherscan`'s own
        docstring for why there is no separate reference-vs-publication
        distinction to get wrong here) is after the candle it's being
        asked about.
        """
        points = ctx.external_data.get(ETHERSCAN_SOURCE, ())
        values: list[FeatureValue] = [
            most_recent_value_at_or_before(points, candle.open_time) for candle in ctx.candles
        ]
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="eth_gas_price",
                        label="Ethereum Gas Price",
                        description="Most recent known Ethereum gas price at or before this "
                        "candle.",
                        dtype="float",
                    ),
                    values=values,
                )
            ]
        )
