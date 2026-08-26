"""Experiment data access repository.

All SQL for the Experiment Management System lives here; the service layer
never builds queries directly, matching this codebase's existing
repository/service split (`repositories/candles.py`, `repositories/markets.py`).

This is the platform's first *write* repository — every other repository
so far is read-only, since Market/Candle rows are populated by the sync/
ingest services rather than a CRUD API. `get_db`'s own contract ("callers
are expected to commit explicitly") is honored here: each mutating method
commits its own unit of work and refreshes the instance, so a caller never
has to know the session is dirty.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from app.models.experiment import (
    Experiment,
    ExperimentArtifact,
    ExperimentMetric,
    ExperimentTag,
)

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "name": Experiment.name,
    "status": Experiment.status,
    "model_type": Experiment.model_type,
    "created_at": Experiment.created_at,
    "updated_at": Experiment.updated_at,
}

#: Eagerly loads every child collection an experiment response needs, in
#: one query — a list or detail response never triggers a lazy load.
_WITH_CHILDREN = (
    selectinload(Experiment.tags),
    selectinload(Experiment.metrics),
    selectinload(Experiment.artifacts),
)


@dataclass
class ExperimentFilters:
    """Search/filter criteria for listing experiments — a plain data holder, not a query builder."""

    search: str | None = None
    status: str | None = None
    model_type: str | None = None
    dataset_version: str | None = None
    tag: str | None = None


class ExperimentRepository:
    """CRUD and search/filter/sort access to experiments and their children."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, experiment: Experiment) -> Experiment:
        self.session.add(experiment)
        await self.session.commit()
        return await self.get_by_id(experiment.id)  # type: ignore[return-value]

    async def get_by_id(self, experiment_id: uuid.UUID) -> Experiment | None:
        result = await self.session.execute(
            select(Experiment).where(Experiment.id == experiment_id).options(*_WITH_CHILDREN)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        filters: ExperimentFilters,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Experiment], int]:
        """Return one page of experiments matching `filters`, plus the total match count."""
        query = select(Experiment)
        count_query = select(func.count()).select_from(Experiment)

        if filters.search:
            pattern = f"%{filters.search}%"
            condition = Experiment.name.ilike(pattern) | Experiment.notes.ilike(pattern)
            query = query.where(condition)
            count_query = count_query.where(condition)
        if filters.status:
            query = query.where(Experiment.status == filters.status)
            count_query = count_query.where(Experiment.status == filters.status)
        if filters.model_type:
            query = query.where(Experiment.model_type == filters.model_type)
            count_query = count_query.where(Experiment.model_type == filters.model_type)
        if filters.dataset_version:
            query = query.where(Experiment.dataset_version == filters.dataset_version)
            count_query = count_query.where(Experiment.dataset_version == filters.dataset_version)
        if filters.tag:
            tag_match = select(ExperimentTag.experiment_id).where(ExperimentTag.tag == filters.tag)
            query = query.where(Experiment.id.in_(tag_match))
            count_query = count_query.where(Experiment.id.in_(tag_match))

        total = (await self.session.execute(count_query)).scalar_one()

        column = SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = query.options(*_WITH_CHILDREN).order_by(order, Experiment.id.asc())
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().unique()), total

    async def update(self, experiment: Experiment, fields: dict[str, Any]) -> Experiment:
        """Apply a partial update. `fields` is expected to already be filtered to only
        the keys the caller explicitly set (e.g. via Pydantic's `exclude_unset`), so
        every key here is applied unconditionally — including an explicit `None`,
        which is how a nullable field (e.g. `model_type`) is cleared."""
        for key, value in fields.items():
            setattr(experiment, key, value)
        await self.session.commit()
        return await self.get_by_id(experiment.id)  # type: ignore[return-value]

    async def replace_tags(self, experiment: Experiment, tags: list[str]) -> Experiment:
        """Replace an experiment's full tag set with `tags` (deduplicated, order-preserving)."""
        deduped = list(dict.fromkeys(tags))
        current = {t.tag for t in experiment.tags}
        for existing in list(experiment.tags):
            if existing.tag not in deduped:
                await self.session.delete(existing)
        for tag in deduped:
            if tag not in current:
                self.session.add(ExperimentTag(experiment_id=experiment.id, tag=tag))
        await self.session.commit()
        # `expire_on_commit=False` means the just-committed `experiment.tags`
        # collection is not automatically invalidated, so a caller reading it
        # directly (rather than through `get_by_id`) would see the pre-commit
        # state. Expiring it here forces `get_by_id`'s own `selectinload` to
        # actually reload it from the database.
        self.session.expire(experiment, ["tags"])
        return await self.get_by_id(experiment.id)  # type: ignore[return-value]

    async def delete(self, experiment: Experiment) -> None:
        await self.session.delete(experiment)
        await self.session.commit()

    async def add_metric(self, metric: ExperimentMetric) -> ExperimentMetric:
        self.session.add(metric)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def get_metric(
        self, experiment_id: uuid.UUID, metric_id: uuid.UUID
    ) -> ExperimentMetric | None:
        result = await self.session.execute(
            select(ExperimentMetric).where(
                ExperimentMetric.id == metric_id,
                ExperimentMetric.experiment_id == experiment_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_metric(self, metric: ExperimentMetric) -> None:
        await self.session.delete(metric)
        await self.session.commit()

    async def add_artifact(self, artifact: ExperimentArtifact) -> ExperimentArtifact:
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def get_artifact(
        self, experiment_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> ExperimentArtifact | None:
        result = await self.session.execute(
            select(ExperimentArtifact).where(
                ExperimentArtifact.id == artifact_id,
                ExperimentArtifact.experiment_id == experiment_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_artifact(self, artifact: ExperimentArtifact) -> None:
        await self.session.delete(artifact)
        await self.session.commit()
