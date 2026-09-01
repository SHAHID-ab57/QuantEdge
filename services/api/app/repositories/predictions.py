"""Prediction History repository — the Live Prediction Service's data access layer.

Mirrors `repositories/evaluation_benchmark_runs.py`'s CRUD/search shape
exactly — the same "write once, list/get" convention every history-style
repository on this platform already follows.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.prediction import Prediction

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "symbol": Prediction.symbol,
    "as_of": Prediction.as_of,
    "created_at": Prediction.created_at,
}


@dataclass
class PredictionFilters:
    """Search/filter criteria for listing past predictions."""

    training_job_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    symbol: str | None = None


class PredictionRepository:
    """Create and search/filter/sort access to persisted predictions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, prediction: Prediction) -> Prediction:
        self.session.add(prediction)
        await self.session.commit()
        await self.session.refresh(prediction)
        return prediction

    async def get_by_id(self, prediction_id: uuid.UUID) -> Prediction | None:
        return await self.session.get(Prediction, prediction_id)

    async def search(
        self,
        filters: PredictionFilters,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Prediction], int]:
        """Return one page of past predictions matching `filters`, plus the total count."""
        query = select(Prediction)
        count_query = select(func.count()).select_from(Prediction)

        if filters.training_job_id is not None:
            query = query.where(Prediction.training_job_id == filters.training_job_id)
            count_query = count_query.where(Prediction.training_job_id == filters.training_job_id)
        if filters.experiment_id is not None:
            query = query.where(Prediction.experiment_id == filters.experiment_id)
            count_query = count_query.where(Prediction.experiment_id == filters.experiment_id)
        if filters.symbol:
            query = query.where(Prediction.symbol == filters.symbol)
            count_query = count_query.where(Prediction.symbol == filters.symbol)

        total = (await self.session.execute(count_query)).scalar_one()

        column = SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = query.order_by(order, Prediction.id.asc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total
