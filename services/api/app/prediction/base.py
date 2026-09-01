"""The prediction outcome contract.

Mirrors `app/evaluation/base.py`'s own split: a small, framework-free
dataclass describing what one prediction produced, with nothing here aware
of the database, the model adapter registry, or how a feature vector was
reconstructed. `app/prediction/engine.py` is the one place that assembles
this from a completed job's own prediction response.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PredictionOutcome:
    """One live prediction's shape — never a bare number.

    `confidence`/`probabilities` are `None` together whenever the
    underlying model adapter has no `predict_proba` (every regressor,
    today) — `confidence_unavailable_reason` then explains why in the same
    words a response body and a frontend panel both show, so "no
    confidence" always reads as an honest, explained absence rather than a
    silently missing field.
    """

    target_column: str
    #: The target generator's own configured horizon (candles ahead), read
    #: from the experiment's `target_config` — `None` only if it could not
    #: be resolved (e.g. a hand-edited `target_config` missing the entry).
    horizon: int | None
    #: The candle timestamp the feature vector was actually computed from —
    #: which may differ from a caller-requested `as_of` by up to one candle
    #: interval, since this is always a real stored candle's own open time,
    #: never an interpolated instant.
    as_of: datetime
    predicted_value: Any
    #: The predicted class's own probability (0-1), for a classifier.
    #: `None` for a regressor, or for any adapter without `predict_proba`.
    confidence: float | None
    #: Set only when `confidence` is `None`, explaining why in the same
    #: terms `TrainingJobPredictResponse` itself already uses.
    confidence_unavailable_reason: str | None
    #: Every class's own probability, keyed by its label — `None` under the
    #: same condition as `confidence`.
    probabilities: dict[str, float] | None
    #: The model's class labels, in the same order training/prediction
    #: already use — `None` for a regressor.
    classes: list[Any] | None
