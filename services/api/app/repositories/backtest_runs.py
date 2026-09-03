"""Backtest run data access repository.

All SQL for backtests lives here; the service layer never builds queries
directly — the same repository/service split every other domain on this
platform already follows.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.backtest_run import BacktestRun

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "symbol": BacktestRun.symbol,
    "status": BacktestRun.status,
    "created_at": BacktestRun.created_at,
    "started_at": BacktestRun.started_at,
    "completed_at": BacktestRun.completed_at,
}


@dataclass
class BacktestRunFilters:
    """Search/filter criteria for listing past backtest runs."""

    training_job_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    symbol: str | None = None
    status: str | None = None


class BacktestRunRepository:
    """CRUD, atomic lifecycle transition, and search/filter/sort access to backtest runs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run: BacktestRun) -> BacktestRun:
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> BacktestRun | None:
        return await self.session.get(BacktestRun, run_id)

    async def try_transition_to_running(self, run_id: uuid.UUID) -> BacktestRun | None:
        """Atomically move `run_id` from 'pending' to 'running', or fail closed.

        The exact same atomic `UPDATE ... WHERE status = 'pending'` guard
        `TrainingJobRepository.try_transition_to_running` uses — mirrored,
        not reinvented, even though a backtest run's own row can never
        actually be raced the way a training job's can (each
        `POST /backtests/run` call creates a brand-new row; there is no
        second endpoint that could call this on an already-`pending` row
        concurrently). Kept anyway: it's the one correct way to make this
        transition, race or not, and diverging from the established pattern
        for a case that merely doesn't need it would be its own kind of
        inconsistency.
        """
        result = await self.session.execute(
            update(BacktestRun)
            .where(BacktestRun.id == run_id, BacktestRun.status == "pending")
            .values(status="running", started_at=datetime.now(UTC))
        )
        await self.session.commit()
        # See `TrainingJobRepository.try_transition_to_running`'s own comment:
        # a Core DML `update()` always yields a `CursorResult` at runtime,
        # narrowed here rather than assumed via `cast`/`# type: ignore`.
        assert isinstance(result, CursorResult)
        if result.rowcount == 0:
            return None
        return await self.get_by_id(run_id)

    async def update(self, run: BacktestRun, fields: dict[str, Any]) -> BacktestRun:
        """Apply a partial update. Every key in `fields` is applied unconditionally,
        including an explicit `None` — the same "caller already filtered the keys"
        contract every other repository's own `update` uses."""
        for key, value in fields.items():
            setattr(run, key, value)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def search(
        self,
        filters: BacktestRunFilters,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[BacktestRun], int]:
        """Return one page of past backtest runs matching `filters`, plus the total count."""
        query = select(BacktestRun)
        count_query = select(func.count()).select_from(BacktestRun)

        if filters.training_job_id is not None:
            query = query.where(BacktestRun.training_job_id == filters.training_job_id)
            count_query = count_query.where(BacktestRun.training_job_id == filters.training_job_id)
        if filters.experiment_id is not None:
            query = query.where(BacktestRun.experiment_id == filters.experiment_id)
            count_query = count_query.where(BacktestRun.experiment_id == filters.experiment_id)
        if filters.symbol:
            query = query.where(BacktestRun.symbol == filters.symbol)
            count_query = count_query.where(BacktestRun.symbol == filters.symbol)
        if filters.status:
            query = query.where(BacktestRun.status == filters.status)
            count_query = count_query.where(BacktestRun.status == filters.status)

        total = (await self.session.execute(count_query)).scalar_one()

        column = SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = query.order_by(order, BacktestRun.id.asc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total
