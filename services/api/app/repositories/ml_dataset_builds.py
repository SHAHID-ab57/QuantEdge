"""ML dataset build history repository — Dataset History's data access layer.

Mirrors `repositories/experiments.py`'s CRUD/search shape exactly, the same
convention every write-backed repository on this platform already follows.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.ml_dataset_build import MLDatasetBuild

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "symbol": MLDatasetBuild.symbol,
    "timeframe": MLDatasetBuild.timeframe,
    "row_count": MLDatasetBuild.row_count,
    "created_at": MLDatasetBuild.created_at,
}


@dataclass
class MLDatasetBuildFilters:
    """Search/filter criteria for listing past ML dataset builds."""

    symbol: str | None = None
    timeframe: str | None = None
    quality_passed: bool | None = None


class MLDatasetBuildRepository:
    """CRUD and search/filter/sort access to persisted ML dataset builds."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, build: MLDatasetBuild) -> MLDatasetBuild:
        self.session.add(build)
        await self.session.commit()
        await self.session.refresh(build)
        return build

    async def get_by_id(self, build_id: uuid.UUID) -> MLDatasetBuild | None:
        return await self.session.get(MLDatasetBuild, build_id)

    async def search(
        self,
        filters: MLDatasetBuildFilters,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[MLDatasetBuild], int]:
        """Return one page of past builds matching `filters`, plus the total match count."""
        query = select(MLDatasetBuild)
        count_query = select(func.count()).select_from(MLDatasetBuild)

        if filters.symbol:
            query = query.where(MLDatasetBuild.symbol == filters.symbol)
            count_query = count_query.where(MLDatasetBuild.symbol == filters.symbol)
        if filters.timeframe:
            query = query.where(MLDatasetBuild.timeframe == filters.timeframe)
            count_query = count_query.where(MLDatasetBuild.timeframe == filters.timeframe)
        if filters.quality_passed is not None:
            query = query.where(MLDatasetBuild.quality_passed == filters.quality_passed)
            count_query = count_query.where(MLDatasetBuild.quality_passed == filters.quality_passed)

        total = (await self.session.execute(count_query)).scalar_one()

        column = SORT_COLUMNS[sort]
        order = column.desc() if direction == "desc" else column.asc()
        query = query.order_by(order, MLDatasetBuild.id.asc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def delete(self, build: MLDatasetBuild) -> None:
        await self.session.delete(build)
        await self.session.commit()
