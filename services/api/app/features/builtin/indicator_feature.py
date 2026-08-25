"""Adapter exposing any registered *indicator* as a feature generator.

This module is the single most important reuse decision in the Feature
Engineering context, so it is worth stating plainly why it exists.

SMA, EMA, and WMA are required feature generators. They are also already
implemented, optimised, and tested in ``app/indicators/builtin/``. Writing
them a second time here would mean two implementations of the same maths
that must agree forever — and the moment they disagree, models train on one
definition of "SMA(20)" and the live chart shows another. That is
*training/serving skew*, the exact failure mode the Feature Engineering
bounded context exists to prevent (``docs/architecture/DomainModel.md``
§ BC3: "Feature computation must be identical for training and inference").

So no moving-average maths is written here at all. ``IndicatorFeature``
wraps an indicator by name and delegates every computation to the shared
``IndicatorEngine``, deriving its own catalogue metadata from the
indicator's. The consequences are worth having:

- SMA/EMA/WMA features are three constructor calls, not three modules.
- Every *future* indicator becomes available as a feature the moment it is
  registered — no feature-side change at all.
- A fix to an indicator's maths fixes the feature in the same commit, by
  construction.
- Indicator results are served from the engine's own ``IndicatorCache``,
  so a chart overlay and a dataset column computed from identical inputs
  cost one calculation between them, not two.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
)
from app.indicators.engine import IndicatorEngine


def _column_suffix(params: Mapping[str, Any]) -> str:
    """Build a stable, readable column suffix from the resolved parameters.

    ``{"period": 20, "source": "close"}`` becomes ``20`` and
    ``{"period": 20, "source": "high"}`` becomes ``20_high``: the
    conventional default (``close``) is omitted so the common case reads as
    ``sma_20`` rather than ``sma_20_close``, while a non-default source is
    always visible in the column name — a dataset column must never hide a
    parameter that changes its values.
    """
    parts: list[str] = []
    for key in sorted(params):
        value = params[key]
        if key == "source" and value == "close":
            continue
        parts.append(str(value))
    return "_".join(parts)


class IndicatorFeature(FeatureGenerator):
    """Exposes one registered indicator as a feature generator.

    Constructed rather than subclassed (see ``registry.register_generator``):
    the wrapped indicator's name is the only thing that varies, so three
    near-identical subclasses would be pure duplication.
    """

    def __init__(self, indicator_name: str, engine: IndicatorEngine) -> None:
        self._indicator_name = indicator_name
        self._engine = engine
        indicator = engine.describe(indicator_name)
        # Metadata is *derived*, never restated: label, description,
        # parameter specs, complexity and warmup semantics all come from
        # the indicator itself, so they cannot drift out of sync with it.
        self.metadata = FeatureMetadata(
            name=indicator_name,
            label=indicator.label,
            description=indicator.description,
            category=indicator.category,
            parameters=indicator.parameters,
            outputs=(f"{indicator_name}_{{period}}",),
            version=indicator.version,
            author=indicator.author,
            complexity=indicator.complexity,
            warmup_description=indicator.warmup_description,
            aliases=indicator.aliases,
            # Same units as whichever candle field the `source` parameter
            # selects (close by default) — a moving average of price is
            # still priced in the source's units.
            unit="price",
            value_type="float",
            is_deterministic=True,
            missing_values_expected=False,
        )

    @property
    def indicator_name(self) -> str:
        """The registered indicator this feature delegates to."""
        return self._indicator_name

    def warmup(self, params: Mapping[str, Any]) -> int:
        """Defer to the wrapped indicator's own warmup rule."""
        return self._engine.registry.get(self._indicator_name).warmup(params)

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Run the indicator through the shared engine and relabel its series.

        The parameters have already been validated against the indicator's
        own specs by the feature pipeline (they are literally the same
        ``ParameterSpec`` objects), so the engine re-validating them here is
        a cheap idempotent no-op rather than a second, divergent check.
        """
        run = self._engine.run(self._indicator_name, ctx.candles, ctx.params)
        suffix = _column_suffix(run.params)
        return FeatureOutput(
            series=[
                FeatureSeries(
                    column=FeatureColumn(
                        name=self._column_name(series.name, suffix),
                        label=series.label,
                        description=self.metadata.description,
                        dtype="float",
                    ),
                    values=list(series.values),
                )
                for series in run.output.series
            ]
        )

    def _column_name(self, series_name: str, suffix: str) -> str:
        """``sma`` + ``20`` → ``sma_20``; a multi-series indicator keeps its series name."""
        return f"{series_name}_{suffix}" if suffix else series_name


def register_indicator_features(
    names: Sequence[str],
    engine: IndicatorEngine,
    registry: Any,
) -> list[IndicatorFeature]:
    """Register one ``IndicatorFeature`` per named indicator.

    Skips a name that is already registered as a feature, so this is safe
    to call more than once — the builtin loader is idempotent and tests
    build isolated registries from the same helper.
    """
    created: list[IndicatorFeature] = []
    for name in names:
        if registry.has(name):
            continue
        feature = IndicatorFeature(name, engine)
        registry.register_generator(feature)
        created.append(feature)
    return created
