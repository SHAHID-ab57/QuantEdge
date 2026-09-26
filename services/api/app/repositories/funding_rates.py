"""Funding-rate history data access (`FundingRate`).

All SQL for this table lives here; the ingest and settlement services never
build queries directly.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funding_rate import FundingRate


class FundingRateRepository:
    """Idempotent upsert and lookup of a market's funding rate at a funding time."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, market_id: uuid.UUID, funding_time: datetime) -> FundingRate | None:
        result = await self.session.execute(
            select(FundingRate).where(
                FundingRate.market_id == market_id, FundingRate.funding_time == funding_time
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        market_id: uuid.UUID,
        funding_time: datetime,
        *,
        funding_rate: Decimal,
        index_price: Decimal,
        mark_price: Decimal | None,
    ) -> bool:
        """Insert or refresh the row for `(market_id, funding_time)`; returns
        whether a row was newly created. Re-ingesting the same window is a
        no-op in effect, which is what makes catch-up ingestion safe."""
        existing = await self.get(market_id, funding_time)
        if existing is None:
            self.session.add(
                FundingRate(
                    market_id=market_id,
                    funding_time=funding_time,
                    funding_rate=funding_rate,
                    index_price=index_price,
                    mark_price=mark_price,
                )
            )
            await self.session.commit()
            return True
        existing.funding_rate = funding_rate
        existing.index_price = index_price
        existing.mark_price = mark_price
        await self.session.commit()
        return False
