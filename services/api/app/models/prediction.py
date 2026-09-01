"""Prediction model — the Live Prediction Service's persistent record.

One row per `POST /predictions/run` call: which training job and experiment
produced it, the market/timeframe/target/horizon it predicted, the exact
candle timestamp its feature vector was computed from, the predicted value
itself, and — deliberately, from day one — an `actual_outcome` column left
`NULL`. No grading task exists yet (a separate, later milestone item); this
column exists now so that task never needs a schema migration of its own,
the same "reserve the column before the feature that fills it" choice this
platform has no prior precedent for but is the obviously correct one here:
adding a nullable column to an existing table later is free, but every row
recorded before that migration would otherwise be permanently ungradable.

Stores `probabilities`/`classes`/`feature_columns` verbatim (small by
construction — a handful of classes, a few dozen feature names) rather than
re-deriving them from the linked training job on every read, the same
"store the whole answer, never re-compute for history" precedent
`EvaluationBenchmarkRun` already set for Benchmark History.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin


class Prediction(BaseModel, TimestampMixin):
    """One live prediction, from a completed training job's serialized model."""

    __tablename__ = "predictions"

    training_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Denormalized from the job for cheap filtering (`GET /predictions?experiment_id=`)
    #: without a join — the same choice `TrainingJob.dataset_version`/`target_column`
    #: already made relative to their own parent `Experiment`.
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    target_column: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="The resolved target column this job predicts, e.g. 'next_direction_1'.",
    )
    horizon: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Candles ahead this target predicts, read from the experiment's target_config.",
    )
    as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="The stored candle's own open_time the feature vector was computed from.",
    )
    predicted_value: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
        comment="A class label (str) for a classifier, or a number for a regressor.",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="The predicted class's own probability (0-1); NULL for a regressor.",
    )
    probabilities: Mapped[dict[str, float] | None] = mapped_column(
        JSON, nullable=True, comment="Every class's own probability, keyed by label."
    )
    classes: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="The model's class labels, aligned with probabilities."
    )
    feature_columns: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, comment="The feature columns (in order) the model was given."
    )
    model_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Denormalized from the job, for a cheap list view."
    )
    model_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment="'classification' or 'regression', resolved from the model adapter registry.",
    )
    #: Deliberately always NULL today — reserved for a future prediction-grading
    #: task to fill in once the predicted candle's real outcome is known. No
    #: code in this platform writes to this column yet.
    actual_outcome: Mapped[Any] = mapped_column(
        JSON,
        nullable=True,
        comment="Reserved for a future grading task; always NULL until that exists.",
    )

    __table_args__ = (Index("ix_predictions_job_created_at", "training_job_id", "created_at"),)
