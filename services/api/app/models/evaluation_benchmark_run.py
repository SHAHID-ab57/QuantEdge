"""EvaluationBenchmarkRun — a persisted record of one benchmark comparison.

The Model Evaluation & Benchmarking Engine itself
(`app/evaluation/`, `app/services/evaluation.py`) still computes a
benchmark comparison entirely from already-persisted `TrainingJob` rows —
that read-only design (`ARCHITECTURE.md` § "Model Evaluation & Benchmarking
Engine") is unchanged. This table sits *above* it, the same way
`MLDatasetBuild` sits above the ML Dataset Builder: `EvaluationService.benchmark`
now also persists the exact request and response it produced, so a
researcher can come back later and reopen a past comparison — see
"Benchmark History" in `AI.md`.

Stores the **whole** request and response verbatim (small by construction —
a benchmark response is a short list of candidates and per-metric winners,
nothing row-level like a dataset), so reopening a past run never needs to
re-query `TrainingJob` rows that may have since changed or been deleted.
"""

from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin


class EvaluationBenchmarkRun(BaseModel, TimestampMixin):
    """One persisted `POST /evaluation/benchmark` request/response pair, verbatim."""

    __tablename__ = "evaluation_benchmark_runs"

    dataset_version: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    target_column: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Denormalized from response, for a cheap list view."
    )
    request: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="The BenchmarkRequest this run was made with, verbatim."
    )
    response: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="The full BenchmarkResponse this run produced, verbatim."
    )
