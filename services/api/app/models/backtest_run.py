"""BacktestRun model — the persistent record of one `POST /backtests/run` call.

One row per backtest: which training job/experiment it walked, the
requested and effective date range (a range can be capped — see
`MAX_BACKTEST_STEPS` in `app/core/config.py` — and this row records
whether it actually was, honestly, rather than silently running a shorter
backtest than requested), its lifecycle status, and — once complete — the
aggregate metrics computed over every individual prediction it made.

Mirrors `TrainingJob`'s own lifecycle shape (`status`, `started_at`/
`completed_at`, `error_message`), not `EvaluationBenchmarkRun`'s
synchronous request/response-verbatim shape: a backtest is a long-running,
asynchronous operation with real states to track, the same reason
`TrainingJob` needed a state machine and a plain read-only comparison
(`EvaluationBenchmarkRun`) never did.

Every individual prediction a backtest makes is a real row in the
`predictions` table, tagged via `Prediction.backtest_run_id` (see that
model's own docstring) — this table never duplicates per-step data, only
the run's own identity, request, and aggregate outcome.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin

#: Mirrors `app.training.state_machine.ALLOWED_TRANSITIONS`'s own status
#: value set (minus `cancelled` — a backtest has no cancel action, per this
#: feature's own spec) — `pending` is transient (a backtest run is created
#: and started in the same `POST /backtests/run` call, so no row is ever
#: observed at rest in `pending`), kept only for symmetry with `TrainingJob`
#: and so the same "start" pattern (an atomic `UPDATE ... WHERE status =
#: 'pending'`) is available if a future caller ever needs it.
BACKTEST_STATUSES = ("pending", "running", "completed", "failed")


class BacktestRun(BaseModel, TimestampMixin):
    """One backtest: its request, lifecycle, and (once complete) aggregate outcome."""

    __tablename__ = "backtest_runs"

    training_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Denormalized from the job for cheap filtering, the same choice
    #: `Prediction.experiment_id` already made relative to its own parent.
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Denormalized from the job."
    )
    step: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="The walk step's own timeframe — the job's own timeframe unless a coarser one "
        "was requested.",
    )
    requested_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The date actually walked up to — equals `requested_end` unless
    #: `truncated` is true, in which case `MAX_BACKTEST_STEPS` cut it short.
    effective_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if MAX_BACKTEST_STEPS capped the requested range short.",
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_steps: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="The planned number of steps, after capping."
    )
    completed_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="How many of this run's own predictions were successfully graded.",
    )
    model_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment="'classification' or 'regression', resolved the same way a live prediction's "
        "own model_kind is — from the model adapter registry, not re-derived.",
    )
    #: Filled in once `status` reaches a terminal value. Keyed by metric
    #: name (e.g. `{"accuracy": 0.62, "f1": 0.58}`) — the exact
    #: `EvaluationReport.metrics` shape `app.evaluation.engine.EvaluationEngine.evaluate`
    #: already produces, stored verbatim.
    aggregate_metrics: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="status_valid",
        ),
    )
