"""Wire schemas (DTOs) for the Backtesting Engine API.

Same split as every other domain on this platform: `app/backtest/` stays
framework/database-free, and this module is the one place a backtest
request is validated and a response is assembled.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_serializer

if TYPE_CHECKING:
    from app.models.backtest_run import BacktestRun


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class BacktestRunRequest(BaseModel):
    """Walk one training job's model over a historical date range, one prediction per step."""

    training_job_id: uuid.UUID = Field(
        ..., description="A completed training job with a saved model artifact"
    )
    symbol: str = Field(..., description="Market to walk")
    start: datetime = Field(..., description="First as_of to predict at (inclusive)")
    end: datetime = Field(..., description="Walk stops before this instant (exclusive)")
    step: str | None = Field(
        default=None,
        description=(
            "The walk's own step timeframe, e.g. '1h'. Defaults to the training job's own "
            "timeframe; if given, must be the same as, or coarser than, it — a step finer "
            "than the model's own candle resolution would just re-predict the same row."
        ),
    )


class BacktestRunResponse(BaseModel):
    """One backtest run's full record — its request, lifecycle, and (once complete) outcome."""

    id: str
    training_job_id: str
    experiment_id: str
    symbol: str
    timeframe: str
    step: str
    requested_start: datetime
    requested_end: datetime
    effective_end: datetime = Field(
        description="The date actually walked up to; equals requested_end unless truncated"
    )
    truncated: bool = Field(
        description="True if the requested range needed more steps than this platform allows "
        "in one run, and was capped short — see MAX_BACKTEST_STEPS"
    )
    status: str
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_steps: int = Field(description="The planned number of steps, after capping")
    completed_steps: int
    graded_count: int = Field(
        description="How many of this run's own predictions were successfully graded"
    )
    model_kind: str
    aggregate_metrics: dict[str, float] | None = Field(
        default=None, description="Filled in once status reaches a terminal value"
    )
    created_at: datetime

    @field_serializer(
        "requested_start",
        "requested_end",
        "effective_end",
        "started_at",
        "completed_at",
        "created_at",
    )
    def _serialize_timestamps(self, value: datetime | None) -> str | None:
        return _iso(value) if value is not None else None

    @classmethod
    def from_model(cls, run: "BacktestRun") -> "BacktestRunResponse":
        return cls(
            id=str(run.id),
            training_job_id=str(run.training_job_id),
            experiment_id=str(run.experiment_id),
            symbol=run.symbol,
            timeframe=run.timeframe,
            step=run.step,
            requested_start=run.requested_start,
            requested_end=run.requested_end,
            effective_end=run.effective_end,
            truncated=run.truncated,
            status=run.status,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            total_steps=run.total_steps,
            completed_steps=run.completed_steps,
            graded_count=run.graded_count,
            model_kind=run.model_kind,
            aggregate_metrics=run.aggregate_metrics,
            created_at=run.created_at,
        )


class BacktestSummaryDTO(BaseModel):
    """One row in Backtest History's list — metadata only, to keep the list light.

    Mirrors `BenchmarkRunSummaryDTO`'s own "list is metadata-only, detail is
    the full record" split.
    """

    id: str
    training_job_id: str
    symbol: str
    timeframe: str
    step: str
    status: str
    truncated: bool
    total_steps: int
    completed_steps: int
    graded_count: int
    created_at: datetime
    completed_at: datetime | None = None

    @field_serializer("created_at", "completed_at")
    def _serialize_timestamps(self, value: datetime | None) -> str | None:
        return _iso(value) if value is not None else None

    @classmethod
    def from_model(cls, run: "BacktestRun") -> "BacktestSummaryDTO":
        return cls(
            id=str(run.id),
            training_job_id=str(run.training_job_id),
            symbol=run.symbol,
            timeframe=run.timeframe,
            step=run.step,
            status=run.status,
            truncated=run.truncated,
            total_steps=run.total_steps,
            completed_steps=run.completed_steps,
            graded_count=run.graded_count,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )


class BacktestListResponse(BaseModel):
    """One page of past backtest runs — Backtest History's list view."""

    runs: list[BacktestSummaryDTO]
    total: int
    limit: int
    offset: int


__all__ = [
    "BacktestListResponse",
    "BacktestRunRequest",
    "BacktestRunResponse",
    "BacktestSummaryDTO",
]
