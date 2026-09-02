"""Training job data access repository.

All SQL for the Training Framework lives here; the service layer never
builds queries directly — the same repository/service split
`repositories/experiments.py` already established for this platform's other
write-heavy, CRUD-backed domain.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from app.models.training import TrainingJob, TrainingJobLog

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "status": TrainingJob.status,
    "model_type": TrainingJob.model_type,
    "created_at": TrainingJob.created_at,
    "updated_at": TrainingJob.updated_at,
    "started_at": TrainingJob.started_at,
    "completed_at": TrainingJob.completed_at,
}

#: Eagerly loads the log collection — a detail response never triggers a lazy load.
_WITH_LOGS = (selectinload(TrainingJob.logs),)


@dataclass
class TrainingJobFilters:
    """Search/filter criteria for listing training jobs — a plain data holder."""

    experiment_id: uuid.UUID | None = None
    status: str | None = None
    model_type: str | None = None
    #: Both added for the Model Evaluation & Benchmarking Engine
    #: (`app/services/evaluation.py`), which selects the completed jobs a
    #: benchmark compares by the dataset/target they share — the same two
    #: columns `TrainingJob` already stores per job.
    dataset_version: str | None = None
    target_column: str | None = None


class TrainingJobRepository:
    """CRUD, search/filter/sort, and log access for training jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, job: TrainingJob) -> TrainingJob:
        self.session.add(job)
        await self.session.commit()
        return await self.get_by_id(job.id)  # type: ignore[return-value]

    async def get_by_id(self, job_id: uuid.UUID) -> TrainingJob | None:
        result = await self.session.execute(
            select(TrainingJob).where(TrainingJob.id == job_id).options(*_WITH_LOGS)
        )
        return result.scalar_one_or_none()

    async def try_transition_to_running(self, job_id: uuid.UUID) -> TrainingJob | None:
        """Atomically move `job_id` from 'pending' to 'running', or fail closed.

        A single `UPDATE ... WHERE id = :job_id AND status = 'pending'`
        guards the transition at the database level, not in Python: two
        concurrent callers racing the same job (two overlapping
        `POST /training-jobs/{id}/run` requests, each its own session) can
        never both win, because the database serializes the two `UPDATE`
        statements and only the first to commit still sees a `'pending'`
        row to match — the second's `WHERE` clause matches zero rows.
        `'pending'` is hardcoded here (not looked up from
        `app.training.state_machine.ALLOWED_TRANSITIONS`) because it is
        already the *only* source state that state machine ever allows into
        `'running'` — this method's whole reason to exist is standing in
        for a read-then-check-then-write of that exact rule, done instead
        as one atomic write.

        Returns the freshly updated job when this call won the race,
        `None` when it lost — indistinguishable here from "the job does not
        exist at all"; the caller (`TrainingJobService.start`) tells those
        two apart with its own follow-up read, which carries no race risk
        since it only decides *which error* to raise, not whether the
        transition happens.
        """
        result = await self.session.execute(
            update(TrainingJob)
            .where(TrainingJob.id == job_id, TrainingJob.status == "pending")
            .values(
                status="running",
                current_stage=None,
                error_message=None,
                started_at=datetime.now(UTC),
                completed_at=None,
            )
        )
        await self.session.commit()
        # `AsyncSession.execute` is typed to return the generic `Result[Any]`,
        # but a Core DML statement (this `update()`) always yields a
        # `CursorResult` at runtime — the subclass `.rowcount` actually lives
        # on. Narrowed with `assert isinstance`, not `cast`/`# type: ignore`.
        assert isinstance(result, CursorResult)
        if result.rowcount == 0:
            return None
        return await self.get_by_id(job_id)

    async def search(
        self,
        filters: TrainingJobFilters,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[TrainingJob], int]:
        """Return one page of training jobs matching `filters`, plus the total match count."""
        query = select(TrainingJob)
        count_query = select(func.count()).select_from(TrainingJob)

        if filters.experiment_id is not None:
            query = query.where(TrainingJob.experiment_id == filters.experiment_id)
            count_query = count_query.where(TrainingJob.experiment_id == filters.experiment_id)
        if filters.status:
            query = query.where(TrainingJob.status == filters.status)
            count_query = count_query.where(TrainingJob.status == filters.status)
        if filters.model_type:
            query = query.where(TrainingJob.model_type == filters.model_type)
            count_query = count_query.where(TrainingJob.model_type == filters.model_type)
        if filters.dataset_version:
            query = query.where(TrainingJob.dataset_version == filters.dataset_version)
            count_query = count_query.where(TrainingJob.dataset_version == filters.dataset_version)
        if filters.target_column:
            query = query.where(TrainingJob.target_column == filters.target_column)
            count_query = count_query.where(TrainingJob.target_column == filters.target_column)

        total = (await self.session.execute(count_query)).scalar_one()

        column = SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = query.options(*_WITH_LOGS).order_by(order, TrainingJob.id.asc())
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().unique()), total

    async def update(self, job: TrainingJob, fields: dict[str, Any]) -> TrainingJob:
        """Apply a partial update. Every key in `fields` is applied unconditionally,
        including an explicit `None` — the same "caller already filtered the keys"
        contract `ExperimentRepository.update` uses."""
        for key, value in fields.items():
            setattr(job, key, value)
        await self.session.commit()
        return await self.get_by_id(job.id)  # type: ignore[return-value]

    async def delete(self, job: TrainingJob) -> None:
        await self.session.delete(job)
        await self.session.commit()

    async def add_log(self, log: TrainingJobLog) -> TrainingJobLog:
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        # `expire_on_commit=False` means a `TrainingJob` already loaded earlier in
        # this same session keeps its stale (possibly empty) `logs` collection in
        # its identity map — `selectinload` only reloads a relationship that isn't
        # already populated, so a later `get_by_id` for the same job would still
        # return the old collection without this. Same fix
        # `ExperimentRepository.replace_tags` already applies to `tags`.
        job = await self.session.get(TrainingJob, log.job_id)
        if job is not None:
            self.session.expire(job, ["logs"])
        return log
