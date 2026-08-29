"""Regression metrics: MAE, MSE, RMSE, R².

Ports the exact math `linear_regression.py`'s own (now-removed)
`_regression_metrics` used, so refactoring the adapter to call
`EvaluationEngine` instead changes *where* these numbers come from, never
their values.
"""

import math
from collections.abc import Sequence
from typing import Any

from app.evaluation.base import Metric, MetricMetadata
from app.evaluation.registry import register


@register
class MaeMetric(Metric):
    metadata = MetricMetadata(
        name="mae",
        label="MAE",
        description="Mean Absolute Error — the average absolute size of every prediction's miss.",
        category="regression",
        higher_is_better=False,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import mean_absolute_error

        return float(mean_absolute_error(y_true, y_pred))


@register
class MseMetric(Metric):
    metadata = MetricMetadata(
        name="mse",
        label="MSE",
        description="Mean Squared Error — like MAE, but penalizes large misses more heavily.",
        category="regression",
        higher_is_better=False,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import mean_squared_error

        return float(mean_squared_error(y_true, y_pred))


@register
class RmseMetric(Metric):
    metadata = MetricMetadata(
        name="rmse",
        label="RMSE",
        description="Root Mean Squared Error — MSE brought back to the target's own units.",
        category="regression",
        higher_is_better=False,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import mean_squared_error

        return math.sqrt(float(mean_squared_error(y_true, y_pred)))


@register
class R2Metric(Metric):
    metadata = MetricMetadata(
        name="r2",
        label="R²",
        description=(
            "Coefficient of determination — the fraction of variance in the target "
            "the model explains; 1.0 is a perfect fit, 0.0 is no better than the mean."
        ),
        category="regression",
        higher_is_better=True,
    )

    def compute(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> float:
        from sklearn.metrics import r2_score

        return float(r2_score(y_true, y_pred))
