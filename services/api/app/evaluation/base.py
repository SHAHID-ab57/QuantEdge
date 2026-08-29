"""The metric contract: inputs, outputs, metadata, and the base class.

Mirrors `app/training/base.py`'s own `ModelAdapter` contract exactly, for the
same reason: a new metric is a subclass that declares `metadata` and
implements `compute`, and the registry/engine/API/frontend need no changes
to support it.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

#: What kind of problem a metric applies to — the engine uses this to decide
#: which registered metrics to run for a given model adapter's own
#: `model_kind` (`app/training/base.py`'s `ModelKind`, one value of which,
#: `"placeholder"`, has no metrics registered at all).
MetricCategory = Literal["classification", "regression"]


@dataclass(frozen=True, slots=True)
class MetricMetadata:
    """Everything the catalogue knows about a metric without running it."""

    name: str
    label: str
    description: str
    category: MetricCategory
    #: Whether a *larger* value is better (accuracy, F1, R²) or a *smaller*
    #: one is (MAE, MSE, RMSE) — `benchmark.compare` uses this to pick a
    #: "best" model per metric without hardcoding a direction per name.
    higher_is_better: bool
    #: Whether this metric needs `y_proba` (e.g. ROC-AUC) — `EvaluationEngine`
    #: skips it, rather than erroring, when no probabilities were given.
    requires_probabilities: bool = False
    version: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class MetricResult:
    """One metric's outcome: either a real value, or why it couldn't run."""

    name: str
    value: float | None
    #: Set only when `value` is `None` — e.g. "requires class probabilities,
    #: none were given" — so a skipped metric is visible, never silently
    #: absent from a report.
    skipped_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Every applicable metric's outcome for one set of predictions."""

    model_kind: MetricCategory
    results: list[MetricResult] = field(default_factory=list)

    @property
    def metrics(self) -> dict[str, float]:
        """Only the metrics that actually produced a value — the same flat
        `{name: value}` shape `TrainingResult.metrics` has always used, so
        adapters and `_make_update_experiment_hook` need no change to
        consume this."""
        return {result.name: result.value for result in self.results if result.value is not None}

    @property
    def skipped(self) -> dict[str, str]:
        """Metric name -> reason, for every metric that could not run."""
        return {
            result.name: result.skipped_reason
            for result in self.results
            if result.value is None and result.skipped_reason is not None
        }


class Metric(ABC):
    """Base class for every pluggable metric (Strategy + Registry)."""

    metadata: ClassVar[MetricMetadata]

    @abstractmethod
    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        """Compute this metric's value.

        `y_proba`, when given, is one row per prediction, one column per
        class, aligned with the model's own `classes_` order — the same
        shape `ModelAdapter.predict_proba` already returns. A metric that
        declares `requires_probabilities=True` may assume it is not `None`;
        `EvaluationEngine` never calls `compute` for such a metric otherwise.
        """
