"""The Prediction Engine: assembles one `PredictionOutcome` from an already
completed model run.

Framework-light, mirroring `app/evaluation/benchmark.py`'s own posture: this
module does not touch the database, does not reconstruct a feature vector,
and does not run a model — it only turns a resolved target column, the
experiment's own recorded `target_config`, an as-of timestamp, and the
`TrainingJobPredictResponse` `TrainingJobService.predict` already computed
into one honestly-shaped `PredictionOutcome`. `app/services/prediction.py`
is the one place that does the database/feature-reconstruction/model-run
work and calls this.
"""

from datetime import datetime
from typing import Any

from app.prediction.base import PredictionOutcome
from app.schemas.experiments import TargetRequestDTO
from app.schemas.training import TrainingJobPredictResponse

#: Shown whenever a job's model adapter has no `predict_proba` (every
#: regressor today, and any future adapter that doesn't implement one) —
#: the one sentence every response/frontend surface uses verbatim, so
#: "no confidence" always reads as an explained absence, never a silently
#: missing field.
NO_CONFIDENCE_REASON = (
    "This model does not produce class probabilities (only a classifier's "
    "predict_proba is supported), so no confidence is available for this prediction."
)


def resolve_horizon(target_config: list[TargetRequestDTO] | None, target_column: str) -> int | None:
    """The configured target's own `horizon` parameter, matched by name.

    Every built-in target generator names its output `f"{target}_{horizon}"`
    (`app/ml_datasets/targets/{next_close,next_direction,next_return}.py`),
    so the entry whose `target` is that prefix is the one that produced
    `target_column` — read from the experiment's own recorded
    `target_config` (the authoritative, as-configured value), never
    re-derived by parsing the column name's own numeric suffix, which would
    silently drift the moment a target generator's naming convention did.
    """
    for entry in target_config or []:
        if target_column == entry.target or target_column.startswith(f"{entry.target}_"):
            horizon = entry.params.get("horizon")
            if horizon is None:
                return None
            try:
                return int(horizon)
            except (TypeError, ValueError):
                return None
    return None


class PredictionEngine:
    """Shapes one prediction's response — the one place that decides what
    "confidence" means and never lets a probability-less model report one."""

    def assemble(
        self,
        *,
        target_column: str,
        target_config: list[TargetRequestDTO] | None,
        as_of: datetime,
        predict_response: TrainingJobPredictResponse,
    ) -> PredictionOutcome:
        """Turn one already-computed prediction into an honestly-labeled outcome.

        `predict_response.predictions`/`probabilities` always have exactly one
        row here — `app.services.prediction.PredictionService.run` only ever
        predicts for the single reconstructed feature vector.
        """
        predicted_value: Any = predict_response.predictions[0]
        classes = predict_response.classes
        probabilities_row = (
            predict_response.probabilities[0] if predict_response.probabilities else None
        )

        confidence: float | None = None
        confidence_unavailable_reason: str | None = NO_CONFIDENCE_REASON
        probabilities_map: dict[str, float] | None = None
        if probabilities_row is not None and classes is not None:
            confidence = max(probabilities_row)
            confidence_unavailable_reason = None
            probabilities_map = dict(
                zip((str(label) for label in classes), probabilities_row, strict=True)
            )

        return PredictionOutcome(
            target_column=target_column,
            horizon=resolve_horizon(target_config, target_column),
            as_of=as_of,
            predicted_value=predicted_value,
            confidence=confidence,
            confidence_unavailable_reason=confidence_unavailable_reason,
            probabilities=probabilities_map,
            classes=classes,
        )


#: The prediction engine every request uses — one process-wide, stateless
#: instance, matching `app/evaluation/engine.py`'s own `default_engine`
#: "one shared instance" convention.
default_engine = PredictionEngine()
