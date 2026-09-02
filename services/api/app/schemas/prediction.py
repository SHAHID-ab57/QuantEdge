"""Wire schemas (DTOs) for the Live Prediction Service API.

Same split as every other domain on this platform: `app/prediction/` stays
framework/database-free, and this module is the one place a prediction
request is validated and a response is assembled.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_serializer

from app.prediction.engine import NO_CONFIDENCE_REASON
from app.services.candle_ingest import resolution_duration

if TYPE_CHECKING:
    from app.models.prediction import Prediction


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _available_after(prediction: "Prediction") -> datetime | None:
    """When this prediction's outcome becomes knowable, if it isn't yet.

    `None` once graded (`actual_outcome` is no longer `None`) — there is
    nothing left to wait for. Otherwise `as_of + horizon` candle-intervals,
    the exact instant `PredictionService.grade_pending` starts looking for
    the target candle to have closed and been ingested — computed here so
    the frontend never re-derives timeframe-to-duration math itself.
    """
    if prediction.actual_outcome is not None or prediction.horizon is None:
        return None
    return prediction.as_of + resolution_duration(prediction.timeframe) * prediction.horizon


class PredictionRunRequest(BaseModel):
    """Run a fresh, live prediction for one market, using one completed training job."""

    training_job_id: uuid.UUID = Field(
        ..., description="A completed training job with a saved model artifact"
    )
    symbol: str = Field(..., description="Market to compute a fresh feature vector for")
    as_of: datetime | None = Field(
        default=None,
        description=(
            "Predict as of this candle timestamp instead of the latest available one. "
            "The feature vector is computed from the real stored candle at or before "
            "this instant — never an interpolated one."
        ),
    )


class PredictionResponse(BaseModel):
    """One prediction, never presented as a bare number.

    `confidence`/`probabilities`/`classes` are populated only when the job's model
    adapter supports `predict_proba` (today: `logistic_regression`) — explicitly
    `None`, with `confidence_unavailable_reason` explaining why, for every other
    adapter (every regressor), never a fabricated confidence.
    """

    id: str
    training_job_id: str
    experiment_id: str
    symbol: str
    timeframe: str
    model_type: str
    model_kind: str
    target_column: str
    horizon: int | None = Field(
        default=None, description="Candles ahead this target predicts, if resolvable"
    )
    as_of: datetime = Field(
        description="The stored candle's own open_time the feature vector was computed from"
    )
    predicted_value: Any = Field(
        description="A class label for a classifier, a number for a regressor"
    )
    confidence: float | None = Field(
        default=None,
        description="The predicted class's own probability (0-1); null for a regressor",
    )
    confidence_unavailable_reason: str | None = Field(
        default=None,
        description="Set only when confidence is null, explaining why in plain language",
    )
    probabilities: dict[str, float] | None = Field(
        default=None, description="Every class's own probability, keyed by label"
    )
    classes: list[Any] | None = Field(default=None, description="The model's class labels")
    feature_columns: list[str] = Field(
        description="The feature columns (in order) the model was given"
    )
    actual_outcome: Any | None = Field(
        default=None,
        description="The real observed value once known; null means not yet gradeable",
    )
    is_correct: bool | None = Field(
        default=None,
        description="Classification only: whether predicted_value matched actual_outcome",
    )
    error: float | None = Field(
        default=None,
        description="Regression only: absolute error between predicted_value and actual_outcome",
    )
    graded_at: datetime | None = Field(
        default=None, description="When grading actually ran for this prediction"
    )
    available_after: datetime | None = Field(
        default=None,
        description=(
            "Set only while ungraded: the instant the target candle is expected to have "
            "closed, i.e. when grading can next determine this prediction's outcome"
        ),
    )
    created_at: datetime

    @field_serializer("as_of", "created_at", "graded_at", "available_after")
    def _serialize_timestamps(self, value: datetime | None) -> str | None:
        return _iso(value) if value is not None else None

    @classmethod
    def from_model(cls, prediction: "Prediction") -> "PredictionResponse":
        return cls(
            id=str(prediction.id),
            training_job_id=str(prediction.training_job_id),
            experiment_id=str(prediction.experiment_id),
            symbol=prediction.symbol,
            timeframe=prediction.timeframe,
            model_type=prediction.model_type,
            model_kind=prediction.model_kind,
            target_column=prediction.target_column,
            horizon=prediction.horizon,
            as_of=prediction.as_of,
            predicted_value=prediction.predicted_value,
            confidence=prediction.confidence,
            confidence_unavailable_reason=(
                None if prediction.confidence is not None else NO_CONFIDENCE_REASON
            ),
            probabilities=prediction.probabilities,
            classes=prediction.classes,
            feature_columns=list(prediction.feature_columns),
            actual_outcome=prediction.actual_outcome,
            is_correct=prediction.is_correct,
            error=prediction.error,
            graded_at=prediction.graded_at,
            available_after=_available_after(prediction),
            created_at=prediction.created_at,
        )


class PredictionSummaryDTO(BaseModel):
    """One row in Prediction History's list — metadata only, to keep the list light."""

    id: str
    training_job_id: str
    experiment_id: str
    symbol: str
    timeframe: str
    model_type: str
    model_kind: str
    target_column: str
    horizon: int | None
    as_of: datetime
    predicted_value: Any
    confidence: float | None
    actual_outcome: Any | None = Field(
        default=None,
        description="The real observed value once known; null means not yet gradeable",
    )
    is_correct: bool | None = Field(
        default=None,
        description="Classification only: whether predicted_value matched actual_outcome",
    )
    error: float | None = Field(
        default=None,
        description="Regression only: absolute error between predicted_value and actual_outcome",
    )
    graded_at: datetime | None = Field(
        default=None, description="When grading actually ran for this prediction"
    )
    available_after: datetime | None = Field(
        default=None,
        description="Set only while ungraded: when grading can next determine the outcome",
    )
    created_at: datetime

    @field_serializer("as_of", "created_at", "graded_at", "available_after")
    def _serialize_timestamps(self, value: datetime | None) -> str | None:
        return _iso(value) if value is not None else None

    @classmethod
    def from_model(cls, prediction: "Prediction") -> "PredictionSummaryDTO":
        return cls(
            id=str(prediction.id),
            training_job_id=str(prediction.training_job_id),
            experiment_id=str(prediction.experiment_id),
            symbol=prediction.symbol,
            timeframe=prediction.timeframe,
            model_type=prediction.model_type,
            model_kind=prediction.model_kind,
            target_column=prediction.target_column,
            horizon=prediction.horizon,
            as_of=prediction.as_of,
            predicted_value=prediction.predicted_value,
            confidence=prediction.confidence,
            actual_outcome=prediction.actual_outcome,
            is_correct=prediction.is_correct,
            error=prediction.error,
            graded_at=prediction.graded_at,
            available_after=_available_after(prediction),
            created_at=prediction.created_at,
        )


class PredictionListResponse(BaseModel):
    """One page of past predictions — Prediction History's list view."""

    predictions: list[PredictionSummaryDTO]
    total: int
    limit: int
    offset: int
