"""Candle data access repository.

All SQL for reading candle data lives in this module; services and routers
never build queries themselves.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle


@dataclass
class CandleStats:
    """Aggregate statistics for a candle range (one row of aggregates)."""

    total_candles: int
    highest_price: Decimal | None
    lowest_price: Decimal | None
    average_volume: Decimal | None


class CandleRepository:
    """Database access for OHLCV candles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_candles(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int,
        offset: int,
    ) -> list[Candle]:
        """Return candles for a market/timeframe, ascending by open time.

        ``start``/``end`` form a half-open range ``[start, end)``; when
        omitted no temporal filter is applied.
        """
        query = (
            select(Candle)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
            .order_by(Candle.open_time.asc())
            .limit(limit)
            .offset(offset)
        )
        if start is not None:
            query = query.where(Candle.open_time >= start)
        if end is not None:
            query = query.where(Candle.open_time < end)
        return list((await self._session.execute(query)).scalars())

    async def count_candles(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Count candles for a market/timeframe, honoring the range filter."""
        query = select(func.count()).select_from(Candle).where(
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
        )
        if start is not None:
            query = query.where(Candle.open_time >= start)
        if end is not None:
            query = query.where(Candle.open_time < end)
        return (await self._session.execute(query)).scalar_one()

    async def get_latest_candle(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Candle | None:
        """Return the candle with the newest open time, or ``None``."""
        query = (
            select(Candle)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
            .order_by(Candle.open_time.desc())
            .limit(1)
        )
        if start is not None:
            query = query.where(Candle.open_time >= start)
        if end is not None:
            query = query.where(Candle.open_time < end)
        return (await self._session.execute(query)).scalar_one_or_none()

    async def get_candle_stats(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> CandleStats:
        """Return aggregate statistics for candles in the range.

        ``start``/``end`` form a half-open range ``[start, end)``; when
        omitted no temporal filter is applied. ``total_candles`` is 0 when
        nothing matches — callers decide how to present that.
        """
        conditions = [
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
        ]
        if start is not None:
            conditions.append(Candle.open_time >= start)
        if end is not None:
            conditions.append(Candle.open_time < end)

        aggregate = (
            select(
                func.count().label("total_candles"),
                func.max(Candle.high).label("highest_price"),
                func.min(Candle.low).label("lowest_price"),
                func.avg(Candle.volume).label("average_volume"),
            )
            .select_from(Candle)
            .where(*conditions)
        )
        row = (await self._session.execute(aggregate)).one()
        return CandleStats(
            total_candles=int(row.total_candles),
            highest_price=row.highest_price,
            lowest_price=row.lowest_price,
            average_volume=row.average_volume,
        )

    async def get_first_candle(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Candle | None:
        """Return the candle with the earliest open time in the range."""
        query = (
            select(Candle)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
            .order_by(Candle.open_time.asc())
            .limit(1)
        )
        if start is not None:
            query = query.where(Candle.open_time >= start)
        if end is not None:
            query = query.where(Candle.open_time < end)
        return (await self._session.execute(query)).scalar_one_or_none()

    async def count_all(self) -> int:
        """Return the total number of stored candles."""
        query = select(func.count()).select_from(Candle)
        return int((await self._session.execute(query)).scalar_one())

    async def latest_close_time(self) -> datetime | None:
        """Return the newest stored candle close time, or ``None``.

        Used as the derived "last ingestion time" signal: the most recent
        candle written is the most recent evidence of ingestion.
        """
        query = select(func.max(Candle.close_time))
        return (await self._session.execute(query)).scalar_one_or_none()

    async def candle_exists(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        open_time: datetime | None = None,
    ) -> bool:
        """Return whether candles exist for a market/timeframe.

        When ``open_time`` is given, only that specific bucket is checked.
        """
        exists_stmt = (
            select(Candle.id)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
            .limit(1)
            .exists()
        )
        if open_time is not None:
            exists_stmt = exists_stmt.where(Candle.open_time == open_time)
        return (await self._session.execute(select(exists_stmt))).scalar_one()

    async def get_available_timeframes(self, market_id: uuid.UUID) -> list[str]:
        """Return distinct timeframes that have stored candles, ascending."""
        query = (
            select(Candle.timeframe)
            .where(Candle.market_id == market_id)
            .distinct()
            .order_by(Candle.timeframe.asc())
        )
        return list((await self._session.execute(query)).scalars())