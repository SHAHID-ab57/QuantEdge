"""The Evaluation Engine: runs every applicable registered metric for one
set of predictions.

Framework-light, mirroring `app/training/pipeline.py`'s own "one place that
knows the *shape* of the work" discipline: this module does not know how a
model was fit, does not touch the database, and does not know what an
`Experiment` is — it only turns `(y_true, y_pred, y_proba)` into an
`EvaluationReport`, the same three arguments `LogisticRegressionAdapter`/
`LinearRegressionAdapter` already had on hand when they computed these
numbers inline.
"""

import logging
from collections.abc import Sequence
from typing import Any

from app.evaluation.base import EvaluationReport, MetricResult
from app.evaluation.metrics import load_builtin_metrics
from app.evaluation.registry import MetricRegistry
from app.evaluation.registry import default_registry as default_metric_registry

logger = logging.getLogger("app.evaluation.engine")

#: This engine's own version, independent of any metric's own `version` —
#: bump it if *this composition* changes (e.g. how a skipped metric is
#: reported) even if no individual metric's math does.
EVALUATION_ENGINE_VERSION = "1.0.0"


class EvaluationEngine:
    """Runs every registered metric applicable to one `model_kind`."""

    def __init__(self, registry: MetricRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> MetricRegistry:
        """The registry this engine resolves metrics from."""
        return self._registry

    def evaluate(
        self,
        model_kind: str,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
        y_proba: Sequence[Sequence[float]] | None = None,
    ) -> EvaluationReport:
        """Run every metric registered for `model_kind` over these predictions.

        A metric that raises, or that declares `requires_probabilities=True`
        when `y_proba` is `None`, is recorded as **skipped** (with a reason)
        rather than aborting the rest — the same partial-success contract
        every other engine on this platform already holds itself to. Passing
        a `model_kind` with no registered metrics (e.g. `"placeholder"`)
        simply returns an empty report, not an error.
        """
        if model_kind not in ("classification", "regression"):
            return EvaluationReport(model_kind=model_kind, results=[])  # type: ignore[arg-type]

        results: list[MetricResult] = []
        for metric in self._registry.for_category(model_kind):  # type: ignore[arg-type]
            name = metric.metadata.name
            if metric.metadata.requires_probabilities and y_proba is None:
                results.append(
                    MetricResult(
                        name=name,
                        value=None,
                        skipped_reason="Requires class probabilities; none were given.",
                    )
                )
                continue
            try:
                value = metric.compute(y_true, y_pred, y_proba)
            except Exception as exc:  # noqa: BLE001 - a bad metric must not sink the rest
                logger.warning("Metric %r failed to compute: %s", name, exc)
                results.append(
                    MetricResult(
                        name=name, value=None, skipped_reason=f"{type(exc).__name__}: {exc}"
                    )
                )
                continue
            results.append(MetricResult(name=name, value=float(value)))

        return EvaluationReport(model_kind=model_kind, results=results)  # type: ignore[arg-type]


load_builtin_metrics()

#: The evaluation engine every real model adapter uses — one process-wide
#: instance, matching `app/training/serialization.py`'s own
#: `default_serializer` "one shared instance" convention.
default_engine = EvaluationEngine(default_metric_registry)
