"""Candle-shape features — body, wicks, and direction.

The reference *multi-column, mixed-dtype* generator: four columns from one
pass, three continuous and one categorical. Anyone adding a generator whose
outputs are not all plain floats should follow this file.

Why these four together rather than four separate generators: they are one
decomposition of a single candle — body plus upper wick plus lower wick is
exactly the candle's high-low range, and direction is the sign of the body.
Computing them in one pass keeps that relationship visible and makes the
arithmetic obviously consistent. A researcher who wants only one of them
still gets a single column out of the dataset builder by selecting it.

**Normalization is offered, not assumed.** Raw body/wick sizes are in price
units, so a model trained on them learns thresholds that silently break
when the asset's price level changes. The optional ``normalize`` parameter
divides by the candle's own high-low range, producing scale-free 0-1
fractions that stay comparable across assets and across time. It defaults
to ``false`` so the untransformed values remain the default answer — a
platform that silently normalizes is one whose numbers cannot be checked
by hand against a chart.
"""

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
    FeatureValue,
    OHLCVPoint,
    ParameterSpec,
)
from app.features.registry import register

#: A candle whose high equals its low (a completely flat candle — possible
#: in a thin market) has no range to normalize against. Its fractions are
#: reported as ``None`` rather than as a fabricated 0 or a division error:
#: "undefined here" is the honest answer, and the dataset builder already
#: knows how to drop or keep a null row.
_UNDEFINED: FeatureValue = None


@register
class CandleShapeFeature(FeatureGenerator):
    """Body size, upper wick, lower wick, and direction of each candle."""

    metadata = FeatureMetadata(
        name="candle_shape",
        label="Candle Shape",
        description=(
            "Decomposes each candle into its body size, upper wick, lower wick, "
            "and direction. Together the body and both wicks span the candle's "
            "full high-low range; direction is the sign of the body."
        ),
        category="price_action",
        parameters=(
            ParameterSpec(
                name="normalize",
                type="bool",
                label="Normalize",
                description=(
                    "Divide body and wick sizes by the candle's high-low range, "
                    "producing scale-free 0-1 fractions that stay comparable "
                    "across price levels and assets."
                ),
                default=False,
            ),
        ),
        outputs=("candle_body", "upper_wick", "lower_wick", "candle_direction"),
        version="1.0.0",
        complexity="O(n) — one pass, constant work per candle.",
        warmup_description="None; every column is defined from the first candle.",
        aliases=("body", "wick", "wicks", "direction", "shape", "price action"),
        unit="price, or a 0-1 ratio when `normalize` is set",
        value_type="mixed",
        is_deterministic=True,
        # A flat (zero-range) candle's normalized body/wick fractions are
        # undefined (division by zero avoided, not fabricated as 0) — see
        # `_as_fractions` below. That is a real, expected null beyond the
        # (zero) warmup this generator otherwise never produces.
        missing_values_expected=True,
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Compute all four columns in a single pass over the candles."""
        normalize = ctx.bool_param("normalize")

        bodies: list[FeatureValue] = []
        upper_wicks: list[FeatureValue] = []
        lower_wicks: list[FeatureValue] = []
        directions: list[FeatureValue] = []

        for candle in ctx.candles:
            body = abs(candle.close - candle.open)
            upper = candle.high - max(candle.open, candle.close)
            lower = min(candle.open, candle.close) - candle.low

            if normalize:
                span = candle.high - candle.low
                body, upper, lower = _as_fractions(body, upper, lower, span)

            bodies.append(body)
            upper_wicks.append(upper)
            lower_wicks.append(lower)
            directions.append(_direction(candle))

        unit = "as a fraction of the candle's range" if normalize else "in price units"
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name="candle_body",
                        label="Candle Body",
                        description=f"Absolute distance between open and close, {unit}.",
                        dtype="float",
                    ),
                    values=bodies,
                ),
                FeatureSeries(
                    column=FeatureColumn(
                        name="upper_wick",
                        label="Upper Wick",
                        description=f"Distance from the body's top to the high, {unit}.",
                        dtype="float",
                    ),
                    values=upper_wicks,
                ),
                FeatureSeries(
                    column=FeatureColumn(
                        name="lower_wick",
                        label="Lower Wick",
                        description=f"Distance from the low to the body's bottom, {unit}.",
                        dtype="float",
                    ),
                    values=lower_wicks,
                ),
                FeatureSeries(
                    column=FeatureColumn(
                        name="candle_direction",
                        label="Candle Direction",
                        description=(
                            "'up' when close > open, 'down' when close < open, "
                            "'flat' when they are equal."
                        ),
                        dtype="categorical",
                    ),
                    values=directions,
                ),
            ]
        )


def _as_fractions(
    body: float, upper: float, lower: float, span: float
) -> tuple[FeatureValue, FeatureValue, FeatureValue]:
    """Express the three sizes as fractions of the candle's range.

    A zero range means the candle never moved, so no fraction is defined —
    reported as ``None`` rather than dividing by zero or inventing a value.
    """
    if span <= 0:
        return _UNDEFINED, _UNDEFINED, _UNDEFINED
    return body / span, upper / span, lower / span


def _direction(candle: OHLCVPoint) -> str:
    """Categorical direction of the candle body."""
    if candle.close > candle.open:
        return "up"
    if candle.close < candle.open:
        return "down"
    return "flat"
