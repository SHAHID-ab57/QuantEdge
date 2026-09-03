"""Candle data access repository.

All SQL for reading candle data lives in this module; services and routers
never build queries themselves.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.candle import Candle

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "open_time": Candle.open_time,
    "open": Candle.open,
    "high": Candle.high,
    "low": Candle.low,
    "close": Candle.close,
    "volume": Candle.volume,
}


@dataclass
class CandleStats:
    """Aggregate statistics for a candle range (one row of aggregates)."""

    total_candles: int
    highest_price: Decimal | None
    lowest_price: Decimal | None
    highest_volume: Decimal | None
    lowest_volume: Decimal | None
    average_open: Decimal | None
    average_close: Decimal | None
    average_high: Decimal | None
    average_low: Decimal | None
    average_volume: Decimal | None
    oldest_open: datetime | None
    newest_open: datetime | None
    newest_close: datetime | None


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
        sort: str = "open_time",
        direction: str = "asc",
    ) -> list[Candle]:
        """Return candles for a market/timeframe, ordered by a whitelisted column.

        ``start``/``end`` form a half-open range ``[start, end)``; when
        omitted no temporal filter is applied. ``sort`` must be one of
        ``SORT_COLUMNS``; the default is ascending open time.
        """
        column = SORT_COLUMNS[sort]
        order = column.asc() if direction == "asc" else column.desc()
        query = (
            select(Candle)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
            .order_by(order, Candle.open_time.asc())
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
        query = (
            select(func.count())
            .select_from(Candle)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
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
                func.max(Candle.volume).label("highest_volume"),
                func.min(Candle.volume).label("lowest_volume"),
                func.avg(Candle.open).label("average_open"),
                func.avg(Candle.close).label("average_close"),
                func.avg(Candle.high).label("average_high"),
                func.avg(Candle.low).label("average_low"),
                func.avg(Candle.volume).label("average_volume"),
                func.min(Candle.open_time).label("oldest_open"),
                func.max(Candle.open_time).label("newest_open"),
                func.max(Candle.close_time).label("newest_close"),
            )
            .select_from(Candle)
            .where(*conditions)
        )
        row = (await self._session.execute(aggregate)).one()
        return CandleStats(
            total_candles=int(row.total_candles),
            highest_price=row.highest_price,
            lowest_price=row.lowest_price,
            highest_volume=row.highest_volume,
            lowest_volume=row.lowest_volume,
            average_open=row.average_open,
            average_close=row.average_close,
            average_high=row.average_high,
            average_low=row.average_low,
            average_volume=row.average_volume,
            oldest_open=row.oldest_open,
            newest_open=row.newest_open,
            newest_close=row.newest_close,
        )

    async def count_invalid_ohlc(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Count candles violating OHLC dominance or non-negative volume.

        A candle is invalid when ``high`` is below ``open`` or ``close``,
        ``low`` is above ``open`` or ``close``, ``high`` is below ``low``,
        or ``volume`` is negative — mirroring the validation service rules.
        """
        conditions = [
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
            (
                (Candle.high < Candle.open)
                | (Candle.high < Candle.close)
                | (Candle.low > Candle.open)
                | (Candle.low > Candle.close)
                | (Candle.high < Candle.low)
                | (Candle.volume < 0)
            ),
        ]
        if start is not None:
            conditions.append(Candle.open_time >= start)
        if end is not None:
            conditions.append(Candle.open_time < end)
        query = select(func.count()).select_from(Candle).where(*conditions)
        return int((await self._session.execute(query)).scalar_one())

    async def count_duplicate_open_times(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Count buckets with more than one stored candle.

        The unique key ``(market_id, timeframe, open_time)`` makes exact
        duplicates structurally impossible; this defensive GROUP BY query
        verifies that invariant for the range.
        """
        conditions = [
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
        ]
        if start is not None:
            conditions.append(Candle.open_time >= start)
        if end is not None:
            conditions.append(Candle.open_time < end)
        subquery = (
            select(Candle.open_time)
            .where(*conditions)
            .group_by(Candle.open_time)
            .having(func.count() > 1)
            .subquery()
        )
        return int(
            (await self._session.execute(select(func.count()).select_from(subquery))).scalar_one()
        )

    async def count_out_of_order(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Count candles whose open time falls before the previous close.

        Uses a window function over candles ordered by open time; a candle
        is out of order when it overlaps the previous bucket
        (``open_time < previous close_time``).
        """
        conditions = [
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
        ]
        if start is not None:
            conditions.append(Candle.open_time >= start)
        if end is not None:
            conditions.append(Candle.open_time < end)
        previous_close = func.lag(Candle.close_time).over(order_by=Candle.open_time)
        subquery = (
            select(Candle.open_time, previous_close.label("prev_close"))
            .where(*conditions)
            .subquery()
        )
        query = (
            select(func.count())
            .select_from(subquery)
            .where(subquery.c.open_time < subquery.c.prev_close)
        )
        return int((await self._session.execute(query)).scalar_one())

    async def get_open_times(
        self,
        market_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[datetime]:
        """Return stored open times in the range, ascending."""
        query = (
            select(Candle.open_time)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == timeframe,
            )
            .order_by(Candle.open_time.asc())
        )
        if start is not None:
            query = query.where(Candle.open_time >= start)
        if end is not None:
            query = query.where(Candle.open_time < end)
        return list((await self._session.execute(query)).scalars())

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

    async def get_research_metrics(
        self,
        market_id: uuid.UUID,
    ) -> list[tuple[str, int, datetime, datetime]]:
        """Return ``(timeframe, count, earliest open, latest open)`` per timeframe."""
        query = (
            select(
                Candle.timeframe,
                func.count().label("total"),
                func.min(Candle.open_time).label("oldest"),
                func.max(Candle.open_time).label("newest"),
            )
            .where(Candle.market_id == market_id)
            .group_by(Candle.timeframe)
            .order_by(Candle.timeframe.asc())
        )
        rows = await self._session.execute(query)
        return [(row.timeframe, int(row.total), row.oldest, row.newest) for row in rows]
