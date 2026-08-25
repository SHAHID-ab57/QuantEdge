"""The feature contract: inputs, outputs, metadata, and the base class.

Nothing in this module imports SQLAlchemy, FastAPI, or Pydantic, and no
feature generator should either — the same layering rule
``app/indicators/`` already follows, for the same reason: a generator that
only knows about ``OHLCVPoint`` values can serve the REST API today and,
unchanged, a training job, a backtest, or a live inference path later.

**Training/serving skew is the failure mode this whole context exists to
prevent** (see ``docs/architecture/DomainModel.md`` § BC3). A feature must
compute identically wherever it runs, which is why the contract carries no
notion of "batch" versus "online": there is one ``generate`` and one code
path.

Deliberate reuse: ``OHLCVPoint`` and ``ParameterSpec`` are imported from
``app/indicators/`` rather than redefined. A feature's input *is* a candle
and a feature's parameters *are* validated the same way an indicator's are;
two parallel definitions of either would be a guaranteed source of drift.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from app.indicators.base import OHLCVPoint
from app.indicators.params import ParameterSpec

__all__ = [
    "FeatureColumn",
    "FeatureContext",
    "FeatureGenerator",
    "FeatureMetadata",
    "FeatureOutput",
    "FeatureSeries",
    "FeatureValue",
    "OHLCVPoint",
    "ParameterSpec",
]

#: What one cell of a dataset may hold. ``None`` marks a warmup position
#: where the feature is not yet defined — never a computation failure,
#: which surfaces as an error instead.
FeatureValue = float | int | bool | str | None

#: The declared type of a feature column, for consumers that need to know
#: how to encode it (a model needs to one-hot a categorical, not scale it).
FeatureDType = Literal["float", "int", "bool", "categorical"]


@dataclass(frozen=True, slots=True)
class FeatureColumn:
    """One named column a generator produces.

    ``name`` is the dataset's column key and must be unique within a
    dataset — which is why it is computed by the generator at runtime
    rather than declared statically: the same generator invoked with
    different parameters produces different columns (``sma_20`` and
    ``sma_50``), and a dataset must be able to hold both at once.
    """

    name: str
    label: str
    description: str = ""
    dtype: FeatureDType = "float"


@dataclass(frozen=True, slots=True)
class FeatureSeries:
    """One computed column: its declaration plus one value per input candle.

    ``values`` is aligned index-for-index with the candles the generator
    was given. That alignment is load-bearing — it is what lets the dataset
    builder zip several independently-computed generators into one coherent
    row-oriented matrix without any generator knowing the others exist.
    """

    column: FeatureColumn
    values: list[FeatureValue]


@dataclass(frozen=True, slots=True)
class FeatureOutput:
    """What a generator returns: one or more aligned columns.

    Multi-column output is the normal case, not an edge case: ``ohlcv``
    returns five columns and ``candle_shape`` returns four, because the
    natural unit of feature engineering is a *related group* of values
    computed from one pass over the data.
    """

    series: list[FeatureSeries]


@dataclass(frozen=True, slots=True)
class FeatureContext:
    """Everything a generator is given: the candles and its parameters.

    ``params`` is always complete and already coerced/validated against the
    generator's own ``ParameterSpec`` list — an implementation never has to
    re-check a bound, supply a default, or parse a string.
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

    def bool_param(self, name: str) -> bool:
        """Read a validated ``bool`` parameter."""
        return bool(self.params[name])


@dataclass(frozen=True, slots=True)
class FeatureMetadata:
    """Everything the catalogue knows about a generator without running it.

    Intentionally the same shape as ``IndicatorMetadata``: a client that
    can already render an indicator catalogue can render this one with no
    new code, and the two contexts stay comparable as both grow. As there,
    ``version`` is a *generator-level* semver — bump it when a change to
    ``generate`` would alter previously-computed values, so a dataset
    recorded against version 1.0.0 is known not to be reproducible under
    2.0.0. That signal is the whole point of versioning features
    (``docs/architecture/DataArchitecture.md`` § D6).
    """

    name: str
    label: str
    description: str
    category: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)
    #: Column names this generator produces, as templates for the
    #: catalogue (e.g. ``("sma_{period}",)``). The authoritative names come
    #: from the ``FeatureOutput`` at runtime; these exist so a UI can show
    #: what to expect before computing anything.
    outputs: tuple[str, ...] = field(default_factory=tuple)
    version: str = "1.0.0"
    author: str = "Eth AI Platform"
    complexity: str = "Not documented"
    warmup_description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    #: Free-form unit of the produced values, e.g. ``"price"``, ``"ratio"``,
    #: ``"USD"``, or ``""`` for a dimensionless/categorical output. Not
    #: machine-parsed anywhere today — it exists so a researcher (or a
    #: future normalization step, see ``ai_extensions.py``) knows what a
    #: column's magnitude actually means without reading the generator's
    #: source.
    unit: str = ""
    #: The generator's *predominant* value type, for a catalogue listing
    #: before any column has been computed. Per-column ``dtype`` (on
    #: ``FeatureColumn``) remains the authoritative, always-correct answer
    #: once a generator has run; this is a coarser, generator-level summary
    #: — ``"float"``, ``"int"``, ``"bool"``, ``"categorical"``, or
    #: ``"mixed"`` for a generator whose columns don't all agree (e.g.
    #: ``candle_shape``, three floats plus one categorical).
    value_type: str = "float"
    #: Names of other *registered features* this one depends on. Declared
    #: metadata only today — no generator ships a real dependency, and
    #: ``generate()`` has no mechanism to receive another feature's
    #: computed columns as input. This is the extension point for that:
    #: ``FeatureRegistry.validate_dependencies`` enforces every declared
    #: name exists and that no cycle exists across the whole registry, and
    #: ``validate_feature_requests`` enforces that a dataset request
    #: including this feature also includes each of its dependencies. See
    #: ``ARCHITECTURE.md`` § "Feature Engineering Engine" for the full
    #: extension-point rationale.
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    #: Whether repeated calls with identical candles and parameters always
    #: produce identical output. True for every generator today (plain
    #: arithmetic over fixed inputs); exists for a future generator with
    #: any stochastic or model-dependent step, where a consumer building a
    #: reproducible dataset needs to know determinism cannot be assumed.
    is_deterministic: bool = True
    #: Whether this generator can produce ``None`` values *beyond* its
    #: declared warmup — e.g. ``candle_shape`` with ``normalize=true`` on a
    #: zero-range (flat) candle. ``False`` for a generator whose only nulls
    #: are the leading warmup positions the pipeline already accounts for.
    #: Read by the dataset builder's quality report so an elevated
    #: mid-series null count is explained rather than looking like a bug.
    missing_values_expected: bool = False


class FeatureGenerator(ABC):
    """Base class for every feature generator (Strategy + Registry).

    A new generator is a subclass that declares ``metadata`` and implements
    ``generate``; the pipeline, registry, dataset builder, service, and API
    need no changes to support it — the identical extension guarantee
    ``app/indicators/`` makes, deliberately, so there is one extension
    workflow on this platform rather than two.
    """

    metadata: ClassVar[FeatureMetadata]

    def warmup(self, params: Mapping[str, Any]) -> int:
        """Candles needed before the first fully-defined value.

        Declared separately from ``generate`` so the pipeline can reject an
        under-sized range up front with a specific, actionable error rather
        than returning a column that is entirely ``None``. Defaults to
        ``0`` for a generator that produces a value from the first candle
        (``ohlcv`` and every candle-shape feature).
        """
        del params
        return 0

    @abstractmethod
    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        """Compute this generator's columns over ``ctx.candles``.

        Implementations may assume parameters are valid and that at least
        ``warmup(params)`` candles are present — the pipeline enforces both
        before calling.
        """
