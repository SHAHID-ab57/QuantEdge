"""Raw OHLC columns — `ohlcv.py`'s own four price fields, deliberately
without `volume`.

**Why this exists alongside `ohlcv`, not instead of it** (RETRAIN-WITH-
MINIMUM-WINDOW,
`docs/research/RETRAIN_WINDOW_ANALYSIS.md`): `ohlcv` is one bundled
generator with five fixed outputs — there is no way to request "OHLC but
not volume" through it, and modifying it to drop a column conditionally
would change a five-column baseline every other research document in this
codebase already cites by that exact shape. A feature set that wants
`volume`'s information without its raw, ever-growing absolute scale (see
`volume_log.py`) needs the price columns from *something*, and this is
that something — a second, single-purpose generator, the same size and
shape as every other feature in this package.

`open`/`high`/`low`/`close` here are byte-identical to `ohlcv`'s own —
this is a re-exposure, not a re-derivation — so a feature set built from
`ohlc` + `volume_log` is directly comparable to one built from `ohlcv`
wherever both include the same price columns.
"""

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
)
from app.features.registry import register

_FIELDS = (
    ("open", "Open", "Opening price of the candle."),
    ("high", "High", "Highest price traded during the candle."),
    ("low", "Low", "Lowest price traded during the candle."),
    ("close", "Close", "Closing price of the candle."),
)


@register
class OhlcFeature(FeatureGenerator):
    """The four raw candle price fields, unmodified — `ohlcv` without `volume`."""

    metadata = FeatureMetadata(
        name="ohlc",
        label="OHLC (no volume)",
        description=(
            "The raw open, high, low, and close of each candle, passed through "
            "unmodified — identical to ohlcv's own four price columns, without "
            "volume. Pairs with volume_log for a feature set that wants volume's "
            "information without its raw, ever-growing absolute scale."
        ),
        category="raw",
        parameters=(),
        outputs=("open", "high", "low", "close"),
        version="1.0.0",
        complexity="O(n) — one pass, no arithmetic.",
        warmup_description="None; defined from the first candle.",
        aliases=("ohlc_no_volume",),
        unit="price",
        value_type="float",
        is_deterministic=True,
        missing_values_expected=False,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Project each candle's price fields into their own aligned columns."""
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name=field, label=label, description=description, dtype="float"
                    ),
                    values=[getattr(candle, field) for candle in ctx.candles],
                )
                for field, label, description in _FIELDS
            ]
        )
