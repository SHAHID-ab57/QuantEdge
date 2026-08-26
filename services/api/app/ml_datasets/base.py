"""The target contract: inputs, outputs, metadata, and the base class.

Deliberately **not** a `FeatureGenerator` and **not** registered in the same
registry as one, even though the shapes look similar. That separation is
itself a leakage-prevention mechanism, not an accident of organization: a
target is defined by looking *forward* from a row (tomorrow's close), while
every feature generator looks only *backward or at* it (a warmup window
ending at the current candle). Keeping targets in their own namespace means
a feature request can never accidentally name a target generator — there is
no registry in which `"next_close"` would resolve as a feature — which
structurally rules out the single worst mistake this module exists to
prevent: training a model on its own label disguised as an input feature.

Where the shapes genuinely are the same primitive, they are reused, not
redeclared: `FeatureColumn`/`FeatureValue` (a target column is exactly as
shaped as a feature column), `OHLCVPoint` (both read candles), and
`ParameterSpec`/`validate_parameters` (both validate parameters the same
way). Only the parts that are genuinely different — the metadata's
`horizon` concept, and the forward-looking generation contract — are new.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.features.base import FeatureColumn, FeatureValue, OHLCVPoint
from app.indicators.params import ParameterSpec

__all__ = [
    "FeatureValue",
    "OHLCVPoint",
    "ParameterSpec",
    "TargetColumn",
    "TargetContext",
    "TargetGenerator",
    "TargetMetadata",
    "TargetOutput",
    "TargetSeries",
]

#: A target column is exactly as shaped as a feature column — reused, not
#: redeclared. The engine has no notion of "input vs. label" at this layer;
#: that distinction is tracked one level up, by whichever registry a column
#: name came from.
TargetColumn = FeatureColumn


@dataclass(frozen=True, slots=True)
class TargetSeries:
    """One computed target column: its declaration plus one value per candle.

    ``values`` is aligned index-for-index with the candles the generator
    was given, exactly like `FeatureSeries` — the alignment guarantee that
    lets a target column be appended onto a feature matrix as just another
    column, which is the whole design (see `app/ml_datasets/dataset.py`).
    """

    column: TargetColumn
    values: list[FeatureValue]


@dataclass(frozen=True, slots=True)
class TargetOutput:
    """What a target generator returns: one or more aligned columns."""

    series: list[TargetSeries]


@dataclass(frozen=True, slots=True)
class TargetContext:
    """Everything a target generator is given: the candles and its parameters.

    ``params`` is always complete and already coerced/validated against the
    generator's own `ParameterSpec` list, the same contract `FeatureContext`
    gives a feature generator.
    """

    candles: Sequence[OHLCVPoint]
    params: Mapping[str, Any]

    def int_param(self, name: str) -> int:
        """Read a validated ``int`` parameter."""
        return int(self.params[name])

    def float_param(self, name: str) -> float:
        """Read a validated ``float`` parameter."""
        return float(self.params[name])

    def str_param(self, name: str) -> str:
        """Read a validated ``string`` parameter."""
        return str(self.params[name])


@dataclass(frozen=True, slots=True)
class TargetMetadata:
    """Everything the catalogue knows about a target generator without running it.

    Deliberately parallel to `FeatureMetadata`, with one addition:
    `default_horizon`. A target looks `horizon` candles into the future, so
    its *last* `horizon` rows can never have a defined value — the mirror
    image of a feature's warmup, which leaves its *first* rows undefined.
    A generator may expose `horizon` as one of its own `parameters` (every
    builtin target does, so a researcher can ask for "next 3 candles"
    instead of just "next 1"); `default_horizon` is what applies when the
    caller doesn't override it.
    """

    name: str
    label: str
    description: str
    category: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)
    #: Column-name templates this generator produces, as templates (e.g.
    #: ``("next_close",)`` or ``("return_{horizon}",)``), matching
    #: `FeatureMetadata.outputs`'s exact convention.
    outputs: tuple[str, ...] = field(default_factory=tuple)
    version: str = "1.0.0"
    author: str = "Eth AI Platform"
    #: The generator's predominant value type — ``"float"`` or
    #: ``"categorical"`` — matching `FeatureMetadata.value_type`'s meaning.
    value_type: str = "float"
    default_horizon: int = 1
    is_deterministic: bool = True


class TargetGenerator(ABC):
    """Base class for every prediction-target generator (Strategy + Registry).

    A new target is a subclass that declares ``metadata`` and implements
    ``generate``; the pipeline, registry, dataset builder, service, and API
    need no changes to support it — the identical extension guarantee
    `FeatureGenerator`/`Indicator`/`ValidationRule` already make, applied a
    fourth time to this platform's fourth Strategy+Registry context.
    """

    metadata: ClassVar[TargetMetadata]

    def horizon(self, params: Mapping[str, Any]) -> int:
        """Candles ahead this target looks, given resolved parameters.

        Declared separately from ``generate`` so the pipeline can check an
        under-sized candle range up front with a specific, actionable error
        — the same reason `FeatureGenerator.warmup` is declared separately
        from `generate`. Defaults to reading a ``horizon`` parameter when
        the generator declares one; a generator with a fixed horizon may
        override this instead.
        """
        return int(params.get("horizon", self.metadata.default_horizon))

    @abstractmethod
    def generate(self, ctx: TargetContext) -> TargetOutput:
        """Compute this generator's target columns over ``ctx.candles``.

        Implementations may assume parameters are valid. The last
        ``horizon(params)`` positions of every returned column must be
        ``None`` — there is no future candle to compute them from — and
        every other position must be defined; the pipeline enforces both
        directions of this contract (`TargetAlignmentError` otherwise), so
        a generator that violates it fails loudly rather than silently
        fabricating or hiding a value.
        """
