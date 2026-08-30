"""The model adapter contract: inputs, outputs, metadata, and the base class.

This is the framework's one extension point — "orchestrate future
TensorFlow, PyTorch, and scikit-learn models without being tied to any
specific framework." A concrete integration is a subclass that declares
`metadata` and implements `initialize`/`train`/`predict`; the pipeline,
registry, service, and API need no changes to support it, the same
extension guarantee `FeatureGenerator`/`TargetGenerator`/`ValidationRule`
already make for their own bounded contexts.

Two kinds of adapter exist side by side today:

- `app/training/adapters/placeholder.py`'s `PlaceholderModelAdapter`
  performs **no real training** — it fabricates deterministic metrics so
  the pipeline, lifecycle, and API could be built and tested end to end
  before any real framework was wired in. It declares
  `requires_real_data=False` and never receives a populated `train`/
  `validation`/`test` split.
- `app/training/adapters/logistic_regression.py` and `.../linear_regression.py`
  are **real scikit-learn baseline models** — every professional
  quantitative model this platform eventually adds must outperform them.
  They declare `requires_real_data=True`, so `TrainingJobService` actually
  builds an `MLDataset` (via the existing ML Dataset Builder) and populates
  `TrainingDataset.train`/`validation`/`test` before `train()` runs.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from app.features.ai_extensions import NormalizationStats


@dataclass(frozen=True, slots=True)
class SplitMatrix:
    """One split's numeric feature matrix and target vector, ready for `sklearn.fit`.

    Deliberately plain Python lists, not a numpy array — this module stays
    framework-free (no numpy/sklearn import here), mirroring
    `FeatureGenerator`'s own "framework-free inputs" discipline. Each
    concrete adapter converts to whatever its own framework needs.
    """

    #: One row per example, one column per feature — already restricted to
    #: numeric (`float`/`int`/`bool`) feature columns; a `"categorical"`
    #: feature column is excluded (see `app/training/dataset_loader.py` —
    #: categorical encoding is a documented, not-yet-implemented extension
    #: point, `app/features/ai_extensions.py`'s `CategoricalEncoder`).
    X: list[list[float]]
    #: The target column's value for each row, aligned index-for-index
    #: with `X`. A classification target's values are its category labels
    #: (e.g. `"up"`/`"down"`/`"flat"`), not one-hot encoded — scikit-learn
    #: classifiers accept string labels directly.
    y: list[Any]


@dataclass(frozen=True, slots=True)
class TrainingDataset:
    """A placeholder handle to "the dataset this job trains over" — or, for a
    `requires_real_data` adapter, the real thing.

    `dataset_version` is always present (a citation, the same relationship
    an `Experiment` has to its own dataset build — see `ARCHITECTURE.md` §
    "ML Dataset Builder": the builder never persists a dataset to a table).
    `train`/`validation`/`test` are `None` unless the model adapter
    declared `requires_real_data=True`, in which case
    `TrainingJobService` has already built a real `MLDataset` (reusing
    `MLDatasetService`, never a second dataset-building path) and split it
    chronologically, exactly as `/markets/{symbol}/ml/dataset` would.
    """

    dataset_version: str
    feature_columns: tuple[str, ...] = ()
    target_column: str | None = None
    train: SplitMatrix | None = None
    validation: SplitMatrix | None = None
    test: SplitMatrix | None = None
    #: Per-column statistics fit on `train` alone (`app/training/normalization.py`),
    #: if this dataset was built with `normalize=True` — `None` otherwise. Carried
    #: on the dataset itself (rather than threaded as a separate argument) so a
    #: model adapter's own `train()` can read it directly to label its own
    #: `compute_feature_importance` call, and so `TrainingJobService` can persist
    #: it onto `result_summary` for `predict()` to reapply later.
    normalization: list[NormalizationStats] | None = None
    #: Which transform `normalization` was fit/applied under — `None` when
    #: `normalization` is `None`, otherwise `"zscore"` or `"minmax"`.
    normalization_method: str | None = None


ModelKind = Literal["placeholder", "classification", "regression"]


@dataclass(frozen=True, slots=True)
class ModelAdapterMetadata:
    """Everything the catalogue knows about a model adapter without running it."""

    name: str
    label: str
    description: str
    #: The (future) ML framework this adapter would wrap, e.g. "tensorflow",
    #: "pytorch". `"scikit-learn"` for the two real baseline adapters;
    #: `"placeholder"` for the one that fabricates metrics.
    framework: str
    #: What kind of problem this adapter solves — the frontend uses this to
    #: decide whether to render a confusion matrix or regression metrics,
    #: and `TrainingJobService` uses it to decide which target dtype is
    #: compatible (a `"classification"` adapter accepts a categorical
    #: target; a `"regression"` adapter requires a numeric one).
    model_kind: ModelKind = "placeholder"
    #: Whether this adapter needs a real, loaded `TrainingDataset.train`/
    #: `validation`/`test` split to run `train()` — `False` only for the
    #: placeholder, which fabricates its metrics regardless of what (if
    #: anything) was loaded.
    requires_real_data: bool = False
    #: Hyperparameter names this adapter recognizes, purely for a frontend
    #: hyperparameter editor to render fields for — never validated
    #: server-side beyond basic JSON shape, since a real framework's own
    #: hyperparameter space isn't known yet.
    hyperparameter_hints: tuple[str, ...] = field(default_factory=tuple)
    version: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class TrainingResult:
    """What a model adapter's `train` returns: metrics, a serialized-model reference,
    and a result summary."""

    metrics: dict[str, float]
    #: Where the trained artifact was written — a fabricated
    #: `placeholder://...` URI for the placeholder adapter, or a real
    #: `file://...` URI from `app/training/serialization.py` for a
    #: scikit-learn adapter (loadable again by `predict`).
    artifact_uri: str
    summary: dict[str, Any]


class ModelAdapter(ABC):
    """Base class for every pluggable model adapter (Strategy + Registry)."""

    metadata: ClassVar[ModelAdapterMetadata]

    @abstractmethod
    def initialize(self, hyperparameters: Mapping[str, Any]) -> None:
        """Prepare the adapter for training with the given hyperparameters.

        A real framework integration would build/compile a model here.
        Implementations may raise on invalid hyperparameters; the pipeline
        converts any exception into `ModelInitializationError`.
        """

    @abstractmethod
    def train(self, dataset: TrainingDataset, hyperparameters: Mapping[str, Any]) -> TrainingResult:
        """Run one training pass and return its result.

        Implementations may assume `initialize` already ran successfully.
        The pipeline converts any exception into `TrainingExecutionError`.
        A `requires_real_data` adapter may assume `dataset.train`/
        `validation` are populated — `TrainingJobService` guarantees this
        before `train()` is ever called for such an adapter.
        """

    @abstractmethod
    def predict(self, artifact_uri: str, rows: Sequence[Sequence[float]]) -> list[Any]:
        """Load the model `train` serialized to `artifact_uri` and predict for `rows`.

        Deliberately decoupled from `train()` — a prediction may run in a
        different process, long after the job that produced the model
        finished; nothing here may assume in-memory state a training run
        left behind. `rows` is already restricted to the same numeric
        feature columns `train()` was given (see `SplitMatrix`).
        """

    def predict_proba(
        self, artifact_uri: str, rows: Sequence[Sequence[float]]
    ) -> list[list[float]] | None:
        """Per-class probabilities for `rows`, or `None` if this adapter has none.

        Not abstract — the default `None` is correct for `PlaceholderModelAdapter`
        (no real model) and `LinearRegressionAdapter` (a regressor has no notion of a
        class probability). Only `LogisticRegressionAdapter` overrides this. Callers
        (`TrainingJobService.predict`'s Prediction Confidence output) treat `None` as
        "no probability/confidence available for this model," never as an error.
        """
        return None
