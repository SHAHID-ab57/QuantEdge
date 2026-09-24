"""Grading a persisted prediction against its real, now-known outcome.

Framework-light and database-free, mirroring `app/prediction/engine.py`'s
own posture: this module does not touch the database, does not fetch
candles, and does not know what a `Prediction` ORM row is — it only turns
an already-loaded candle window plus the target generator that produced
the training label into a `GradingOutcome`. `app/services/prediction.py`
(`PredictionService.grade_pending`) is the one place that decides which
predictions are gradeable yet, fetches their candles, and calls this.

Reuses, never reimplements:

- The *exact* `TargetPipeline`/`TargetGenerator` that produced the training
  label (`app.ml_datasets.pipeline.TargetPipeline`, the same one
  `MLDatasetBuilder` drives) — grading runs the identical target function
  over a fresh candle window, never a hand-rolled "is the direction up or
  down" check. Grading is only meaningful if it uses the same definition of
  "correct" the model was trained against; re-deriving that definition here
  would risk silently drifting from it the moment a target generator's own
  logic changed.
- The *existing* `accuracy`/`mae` metrics (`app.evaluation.metrics`) for
  "was this correct" / "how wrong was this" — grading one prediction is
  exactly those metrics computed over a one-element `(y_true, y_pred)`
  pair, not a new formula. `AccuracyMetric.compute([actual], [predicted])`
  is `1.0` or `0.0` (an exact match or not); `MaeMetric.compute([actual],
  [predicted])` is `abs(actual - predicted)` for a single pair — the same
  MAE `EvaluationEngine`/the training reports already use, just evaluated
  on a single sample instead of a whole test split.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.evaluation.registry import MetricRegistry
from app.indicators.base import OHLCVPoint
from app.ml_datasets.pipeline import TargetPipeline


@dataclass(frozen=True, slots=True)
class GradingOutcome:
    """What grading determined for one prediction."""

    actual_outcome: Any
    #: Set only when `model_kind == "classification"`; `None` for a regressor.
    is_correct: bool | None
    #: Set only when `model_kind == "regression"`; `None` for a classifier.
    error: float | None


def grade_one(
    *,
    target_name: str,
    target_params: dict[str, str],
    target_column: str,
    predicted_value: Any,
    model_kind: str,
    candles: Sequence[OHLCVPoint],
    target_pipeline: TargetPipeline,
    metric_registry: MetricRegistry,
    as_of_index: int = 0,
) -> GradingOutcome | None:
    """Compute one prediction's real outcome, or `None` if it can't be determined.

    `candles` must already be exactly the window `PredictionService`
    decided was gradeable: `leading_context + horizon + 1` candles,
    ascending, with the candle the prediction's feature vector was
    computed from (`as_of`) at position `as_of_index` — `0` (the default,
    and every builtin target before `volatility_regime`) for a target
    that only ever looks forward from its own row, `leading_context` for
    one that also needs trailing context (VOLATILITY-STOP-WIDTH; see
    `TargetGenerator.leading_context`'s own docstring). This function
    never decides *whether* a prediction is gradeable (that's a
    data-availability question the caller already answered by
    successfully fetching this window, at this offset); it only computes
    the answer once asked.

    Returns `None` (rather than raising) if the named target produced no
    column matching `target_column`, or if that column's own value at
    `as_of_index` came back `None` despite a full window — both defensive
    cases that should not occur given a correctly-sized, correctly-offset
    window, but a grading pass over many predictions should skip a
    surprising row rather than abort the whole pass.
    """
    run = target_pipeline.run(target_name, candles, target_params)
    series = next((s for s in run.output.series if s.column.name == target_column), None)
    if series is None or as_of_index >= len(series.values):
        return None
    actual_outcome = series.values[as_of_index]
    if actual_outcome is None:
        return None

    is_correct: bool | None = None
    error: float | None = None
    if model_kind == "classification":
        accuracy = metric_registry.get("accuracy")
        is_correct = accuracy.compute([actual_outcome], [predicted_value]) == 1.0
    elif model_kind == "regression":
        mae = metric_registry.get("mae")
        error = mae.compute([actual_outcome], [predicted_value])

    return GradingOutcome(actual_outcome=actual_outcome, is_correct=is_correct, error=error)
