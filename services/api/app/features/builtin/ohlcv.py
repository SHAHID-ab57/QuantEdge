"""Raw OHLCV columns — the baseline feature every dataset starts from.

The simplest possible generator: no parameters, no warmup, one pass, five
columns. Read this first when adding a new feature generator.

Included as a *feature* rather than assumed: a model that consumes engineered
features should get its raw inputs through the same pipeline, versioning,
and export path as everything else, not through a side channel that
bypasses alignment checks and dataset metadata.
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
    ("volume", "Volume", "Base-asset volume traded during the candle."),
)


@register
class OhlcvFeature(FeatureGenerator):
    """The five raw candle fields, unmodified."""

    metadata = FeatureMetadata(
        name="ohlcv",
        label="OHLCV",
        description=(
            "The raw open, high, low, close, and volume of each candle, passed "
            "through unmodified. The baseline inputs every other feature is "
            "derived from."
        ),
        category="raw",
        parameters=(),
        outputs=("open", "high", "low", "close", "volume"),
        version="1.0.0",
        complexity="O(n) — one pass, no arithmetic.",
        warmup_description="None; defined from the first candle.",
        aliases=("raw", "candles", "price"),
        unit="price / base-asset volume",
        value_type="float",
        is_deterministic=True,
        missing_values_expected=False,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Project each candle field into its own aligned column."""
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
