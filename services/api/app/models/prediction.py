"""Prediction model — the Live Prediction Service's persistent record.

One row per `POST /predictions/run` call: which training job and experiment
produced it, the market/timeframe/target/horizon it predicted, the exact
candle timestamp its feature vector was computed from, and the predicted
value itself.

`actual_outcome`/`is_correct`/`error`/`graded_at` are filled in later, once
the target horizon has actually arrived — by `app.prediction.grading` (see
its own module docstring), not at prediction time. All four are `NULL`
until then; `actual_outcome IS NULL` is the one authoritative "still
pending" signal every grading query and the API/frontend both use — never
inferred from any other column. `actual_outcome` reserved this shape from
the very first migration specifically so grading never needed a migration
of its own for *that* column; `is_correct`/`error`/`graded_at` are new here
because "was it right" is a genuinely separate concern from "what actually
happened" the original design left open.

Stores `probabilities`/`classes`/`feature_columns` verbatim (small by
construction — a handful of classes, a few dozen feature names) rather than
re-deriving them from the linked training job on every read, the same
"store the whole answer, never re-compute for history" precedent
`EvaluationBenchmarkRun` already set for Benchmark History.

`backtest_run_id` is `NULL` for every ordinary `POST /predictions/run` call
— the Live Prediction Service itself never sets it, and `PredictionService.run`
is not modified to accept one (see `app/services/backtest.py`'s own module
docstring for why). It is filled in, via a separate, additive
`PredictionRepository.tag_backtest_run` write, only by the Backtesting
Engine, immediately after each of its own steps calls `PredictionService.run`
unmodified — the one thing that distinguishes a backtest-generated
prediction from a live one, so Prediction History's default view
(`PredictionRepository.search`) can exclude backtest predictions and keep
showing only what a live trader/researcher actually asked for right now.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
    #: NULL until the target horizon has arrived and `app.prediction.grading`
    #: has computed a real outcome — the one authoritative "still pending"
    #: signal (never inferred from `is_correct`/`error`/`graded_at`).
    #:
    #: `JSON(none_as_null=True)` is deliberate, not the default: SQLAlchemy's
    #: `JSON` type otherwise stores a Python `None` as the *JSON literal*
    #: `null` (a real, non-NULL value at the SQL level), not a SQL `NULL` —
    #: a well-known SQLAlchemy gotcha that would make `WHERE actual_outcome
    #: IS NULL` (every grading query's own "still pending" filter) match
    #: nothing, ever. Caught by this feature's own tests before it shipped;
    #: see migration `99d6a6e10268` for the one-time data fix this required
    #: for rows already written under the old (default) behavior.
    actual_outcome: Mapped[Any] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
        comment="The real observed value once knowable; NULL means not yet gradeable.",
    )
    is_correct: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="Classification only: predicted_value == actual_outcome. NULL for a regressor.",
    )
    error: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment=(
            "Regression only: absolute error between predicted_value and actual_outcome "
            "(the MAE metric applied to this single prediction). NULL for a classifier."
        ),
    )
    graded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When grading actually ran for this row; NULL until it has.",
    )
    backtest_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment=(
            "Set only for a prediction the Backtesting Engine generated; NULL for every "
            "ordinary live POST /predictions/run call. See this model's own docstring."
        ),
    )

    __table_args__ = (Index("ix_predictions_job_created_at", "training_job_id", "created_at"),)
