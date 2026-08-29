"""Classification metrics: Accuracy, Precision, Recall, F1, ROC-AUC.

Ports the exact math `logistic_regression.py`'s own (now-removed)
`_classification_metrics` used, so refactoring the adapter to call
`EvaluationEngine` instead changes *where* these numbers come from, never
their values.
"""

from collections.abc import Sequence
from typing import Any

from app.evaluation.base import Metric, MetricMetadata
from app.evaluation.registry import register

#: scikit-learn's own type stubs declare `zero_division` as `str`-only, but its
#: runtime also accepts the numeric `0`/`1` these metrics rely on (the same
#: stub-completeness gap `logistic_regression.py` already documented) — a
#: locally `Any`-typed constant, not a real type mismatch.
_ZERO_DIVISION: Any = 0


@register
class AccuracyMetric(Metric):
    metadata = MetricMetadata(
        name="accuracy",
        label="Accuracy",
        description="Fraction of predictions that exactly matched the true label.",
        category="classification",
        higher_is_better=True,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import accuracy_score

        return float(accuracy_score(y_true, y_pred))


@register
class PrecisionMetric(Metric):
    metadata = MetricMetadata(
        name="precision",
        label="Precision",
        description=(
            "Of every prediction for a class, the fraction that were actually that "
            "class (weighted across classes by support)."
        ),
        category="classification",
        higher_is_better=True,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import precision_score

        return float(
            precision_score(y_true, y_pred, average="weighted", zero_division=_ZERO_DIVISION)
        )


@register
class RecallMetric(Metric):
    metadata = MetricMetadata(
        name="recall",
        label="Recall",
        description=(
            "Of every true instance of a class, the fraction the model actually "
            "found (weighted across classes by support)."
        ),
        category="classification",
        higher_is_better=True,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import recall_score

        return float(recall_score(y_true, y_pred, average="weighted", zero_division=_ZERO_DIVISION))


@register
class F1Metric(Metric):
    metadata = MetricMetadata(
        name="f1",
        label="F1 Score",
        description="The harmonic mean of Precision and Recall (weighted across classes).",
        category="classification",
        higher_is_better=True,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import f1_score

        return float(f1_score(y_true, y_pred, average="weighted", zero_division=_ZERO_DIVISION))


@register
class RocAucMetric(Metric):
    """One-vs-rest ROC-AUC, weighted by class support for 3+ classes.

    Requires `y_proba` — skipped by `EvaluationEngine` (never an error) for
    any model that can't produce class probabilities. Assumes `y_proba`'s
    columns are already ordered to match `sorted(set(y_true))` — the same
    convention `app/training/interpretability.py`'s `compute_roc_pr_curves`
    already relies on, since scikit-learn's own `classes_` is always sorted.
    """

    metadata = MetricMetadata(
        name="roc_auc",
        label="ROC-AUC",
        description=(
            "Area under the ROC curve — how well the model ranks the true class "
            "above the others, independent of any decision threshold."
        ),
        category="classification",
        higher_is_better=True,
        requires_probabilities=True,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import roc_auc_score

        if y_proba is None:
            raise ValueError("roc_auc requires y_proba")
        proba_rows = [list(row) for row in y_proba]
        class_count = len(proba_rows[0]) if proba_rows else 0
        if class_count == 2:
            positive_class_scores = [row[1] for row in proba_rows]
            return float(roc_auc_score(y_true, positive_class_scores))
        return float(roc_auc_score(y_true, proba_rows, multi_class="ovr", average="weighted"))
