"""Benchmark History repository — the Model Evaluation & Benchmarking
Engine's persisted-run data access layer.

Mirrors `repositories/ml_dataset_builds.py`'s CRUD/search shape exactly —
the same "write once, list/get/delete" convention every history-style
repository on this platform already follows.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.evaluation_benchmark_run import EvaluationBenchmarkRun

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "dataset_version": EvaluationBenchmarkRun.dataset_version,
    "target_column": EvaluationBenchmarkRun.target_column,
    "candidate_count": EvaluationBenchmarkRun.candidate_count,
    "created_at": EvaluationBenchmarkRun.created_at,
}


@dataclass
class EvaluationBenchmarkRunFilters:
    """Search/filter criteria for listing past benchmark runs."""

    dataset_version: str | None = None
    target_column: str | None = None


class EvaluationBenchmarkRunRepository:
    """CRUD and search/filter/sort access to persisted benchmark runs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run: EvaluationBenchmarkRun) -> EvaluationBenchmarkRun:
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> EvaluationBenchmarkRun | None:
        return await self.session.get(EvaluationBenchmarkRun, run_id)

    async def search(
        self,
        filters: EvaluationBenchmarkRunFilters,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[EvaluationBenchmarkRun], int]:
        """Return one page of past benchmark runs matching `filters`, plus the total count."""
        query = select(EvaluationBenchmarkRun)
        count_query = select(func.count()).select_from(EvaluationBenchmarkRun)

        if filters.dataset_version:
            query = query.where(EvaluationBenchmarkRun.dataset_version == filters.dataset_version)
            count_query = count_query.where(
                EvaluationBenchmarkRun.dataset_version == filters.dataset_version
            )
        if filters.target_column:
            query = query.where(EvaluationBenchmarkRun.target_column == filters.target_column)
            count_query = count_query.where(
                EvaluationBenchmarkRun.target_column == filters.target_column
            )

        total = (await self.session.execute(count_query)).scalar_one()

        column = SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = query.order_by(order, EvaluationBenchmarkRun.id.asc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def delete(self, run: EvaluationBenchmarkRun) -> None:
        await self.session.delete(run)
        await self.session.commit()
