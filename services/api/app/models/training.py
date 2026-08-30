"""TrainingJob model — the Training Framework's persistent job record.

A `TrainingJob` records one attempt at running the placeholder training
pipeline (`app/training/pipeline.py`) against a linked `Experiment`: which
model adapter it used, its hyperparameters, its lifecycle status, the
pipeline stage it last reached, any error, and — once finished — a result
summary. `TrainingJobLog` is a child entity (one row per log line), the
same "growing collection gets its own table" choice `ExperimentMetric`
already made, rather than an ever-appending JSON array column.

Every job belongs to exactly one experiment (`experiment_id`, `NOT NULL`,
`ON DELETE CASCADE`) — unlike an experiment's own `dataset_version` (a
citation string, since the ML Dataset Builder persists nothing), a training
job's home experiment is a real row that already exists by the time a job
is created, so a genuine foreign key is the correct — and available —
relationship here.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin

TRAINING_JOB_STATUSES = ("pending", "running", "completed", "failed", "cancelled")

#: Every job starts here — registered but not yet executed, mirroring
#: `Experiment`'s own `DEFAULT_EXPERIMENT_STATUS = "draft"` starting point.
DEFAULT_TRAINING_JOB_STATUS = "pending"

#: The fixed six-stage sequence `app/training/pipeline.py` executes, in
#: order. `TrainingJob.current_stage` is always one of these while
#: `status == "running"`, and is left at the last-reached stage on failure.
TRAINING_JOB_STAGES = (
    "validate_dataset",
    "load_dataset",
    "initialize_model",
    "execute_training",
    "save_results",
    "update_experiment",
)

TRAINING_LOG_LEVELS = ("debug", "info", "warning", "error")


class TrainingJob(BaseModel, TimestampMixin):
    """One recorded attempt at running the placeholder training pipeline for an experiment."""

    __tablename__ = "training_jobs"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="The dataset citation this job trains over; defaults from the experiment.",
    )
    symbol: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Market symbol to load real candles from; required by a requires_real_data model.",
    )
    timeframe: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Candle timeframe to load, e.g. '1h'; required by a requires_real_data adapter.",
    )
    target_column: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Which built target column to predict; defaults to the first one built.",
    )
    model_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="A registered model adapter name (app/training/registry.py), e.g. 'placeholder'.",
    )
    hyperparameters: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Arbitrary hyperparameters passed verbatim to the model adapter.",
    )
    normalize_features: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "Whether to z-score normalize numeric feature columns (fit on the train "
            "split alone) before a requires_real_data adapter trains/predicts. "
            "Ignored by an adapter that declares requires_real_data=False."
        ),
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=DEFAULT_TRAINING_JOB_STATUS,
        server_default=DEFAULT_TRAINING_JOB_STATUS,
    )
    current_stage: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="The pipeline stage last entered; set while running, frozen on failure.",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Structured failure report (reason/affected_feature/affected_rows/suggested_fix).",
    )
    result_summary: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Fabricated placeholder metrics/summary produced by the model adapter.",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list["TrainingJobLog"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="TrainingJobLog.logged_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="status_valid",
        ),
    )


class TrainingJobLog(BaseModel):
    """One log line recorded during a training job's pipeline execution."""

    __tablename__ = "training_job_logs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="info", server_default="info"
    )
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    job: Mapped["TrainingJob"] = relationship(back_populates="logs")

    __table_args__ = (
        CheckConstraint(
            "level IN ('debug', 'info', 'warning', 'error')",
            name="level_valid",
        ),
        Index("ix_training_job_logs_job_logged_at", "job_id", "logged_at"),
    )
