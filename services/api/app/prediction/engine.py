"""The Prediction Engine: assembles one `PredictionOutcome` from an already
completed model run.

Framework-light, mirroring `app/evaluation/benchmark.py`'s own posture: this
module does not touch the database, does not reconstruct a feature vector,
and does not run a model — it only turns a resolved target column, the
experiment's own recorded `target_config`, an as-of timestamp, and the
`TrainingJobPredictResponse` `TrainingJobService.predict` already computed
into one honestly-shaped `PredictionOutcome`. `app/services/prediction.py`
is the one place that does the database/feature-reconstruction/model-run
work and calls this. One narrow exception to "framework-light": the target
registry (`app.ml_datasets.registry`) is a pure, stateless, already
process-wide catalogue — no DB, no model run, the same shape
`IndicatorFeature` already reuses `IndicatorEngine` for — so
`resolve_horizon` reads a target generator's own `horizon(params)` from it,
below.

**`resolve_horizon` bug fixed here (MODEL-QUALITY-T2):** this function
used to read `entry.params["horizon"]` directly, silently returning `None`
for any target whose own horizon-equivalent parameter isn't literally
named `"horizon"` — every built-in `next_*` target uses that name, but
`triple_barrier` (`max_hours`) and `volatility_regime` (`window_hours`)
don't. A `None` horizon means `_grade_one`
(`app/services/prediction.py`) can never grade the prediction at all
(its very first check), which silently broke both the periodic grading
scheduler and the Backtesting Engine for both new targets — discovered
when a real regime walk-forward backtest of `triple_barrier` graded 0 of
1,920 predictions with no error, anywhere. Reading the horizon from the
generator's own `horizon(params)` instead (the same method
`app.ml_datasets.pipeline.TargetPipeline` already uses to plan a dataset
build) fixes every target, present and future, with no per-target special
case.
"""

from datetime import datetime
from typing import Any

from app.ml_datasets.registry import default_registry as default_target_registry
from app.ml_datasets.targets import load_builtin_targets
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


def resolve_target_entry(
    target_config: list[TargetRequestDTO] | None, target_column: str
) -> TargetRequestDTO | None:
    """The experiment's own recorded target entry that produced `target_column`.

    Every built-in target generator names its output `f"{target}_{horizon}"`
    (`app/ml_datasets/targets/{next_close,next_direction,next_return}.py`),
    so the entry whose `target` is that prefix is the one that produced
    `target_column` — matched here once, so `resolve_horizon` (this
    prediction's own displayed horizon) and `app.prediction.grading`
    (which target *generator* — `entry.target` — to re-run for grading)
    both read the identical authoritative entry rather than each
    re-deriving it their own way.
    """
    for entry in target_config or []:
        if target_column == entry.target or target_column.startswith(f"{entry.target}_"):
            return entry
    return None


def resolve_horizon(target_config: list[TargetRequestDTO] | None, target_column: str) -> int | None:
    """How many candles ahead this target column looks, via the target
    generator's own `horizon(params)` — never a hardcoded `"horizon"` key.

    Read from the experiment's own recorded `target_config` (the
    authoritative, as-configured value) plus the registered generator's own
    horizon rule, never re-derived by parsing the column name's own numeric
    suffix (which would silently drift the moment a target generator's
    naming convention did) and never assuming every target names its own
    look-ahead parameter `"horizon"` (`next_close`/`next_return`/
    `next_direction` do; `triple_barrier`/`volatility_regime` don't — see
    this module's own docstring for the bug that assumption caused).
    """
    entry = resolve_target_entry(target_config, target_column)
    if entry is None:
        return None
    load_builtin_targets()
    if not default_target_registry.has(entry.target):
        return None
    generator = default_target_registry.get(entry.target)
    try:
        return int(generator.horizon(entry.params))
    except Exception:  # noqa: BLE001 - an unresolvable horizon is "unknown", not fatal here
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
