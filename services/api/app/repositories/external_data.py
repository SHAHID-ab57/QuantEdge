"""External data point storage access — one repository for every connector.

All SQL for this table lives here; ingestion and the feature-context
bridge never build queries directly — the same repository/service split
every other domain on this platform already follows.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_data import ExternalDataPoint


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp read back from the database to tz-aware UTC.

    SQLite's `DateTime(timezone=True)` columns round-trip as *naive*
    datetimes even though a tz-aware value was stored (Postgres does not
    have this quirk) — the same platform-specific gap already worked
    around in `app.services.candle_sync._catch_up_window` and
    `app.services.external_data_context._as_utc`. Without this, comparing
    a freshly-fetched, tz-aware `RawDataPoint.timestamp` against a naive
    value read back from this repository silently never matches (naive
    vs. aware datetimes compare unequal rather than raising), which is
    exactly what let `_persist_points`'s own duplicate check pass right
    over a genuine duplicate on SQLite — see
    `tests/services/test_external_data_ingest.py` for the regression test.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ExternalDataRepository:
    """Create/read access to `external_data_points`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, point: ExternalDataPoint) -> ExternalDataPoint:
        self.session.add(point)
        await self.session.commit()
        await self.session.refresh(point)
        return point

    async def list_existing_timestamps(self, source: str, symbol: str | None) -> set[datetime]:
        """Timestamps already stored for this source/symbol.

        The real, backend-portable idempotency check
        `app.services.external_data_ingest` uses *before* inserting — see
        `ExternalDataPoint`'s own docstring for why the unique constraint
        alone cannot be relied on when `symbol` is `NULL`.
        """
        result = await self.session.execute(
            select(ExternalDataPoint.timestamp).where(
                ExternalDataPoint.source == source,
                ExternalDataPoint.symbol.is_(symbol)
                if symbol is None
                else ExternalDataPoint.symbol == symbol,
            )
        )
        return {_as_utc(timestamp) for timestamp in result.scalars()}

    async def list_between(
        self,
        source: str,
        symbol: str | None,
        *,
        start: datetime,
        end: datetime,
    ) -> list[ExternalDataPoint]:
        """Every point for this source/symbol in `[start, end]` (inclusive
        both ends — this table's own convention, distinct from `Candle`'s
        half-open range; see `Connector.fetch`'s own docstring for why),
        ordered oldest first — the order `app.features.base
        .most_recent_value_at_or_before`'s bisect search requires.
        """
        result = await self.session.execute(
            select(ExternalDataPoint)
            .where(
                ExternalDataPoint.source == source,
                ExternalDataPoint.symbol.is_(symbol)
                if symbol is None
                else ExternalDataPoint.symbol == symbol,
                ExternalDataPoint.timestamp >= start,
                ExternalDataPoint.timestamp <= end,
            )
            .order_by(ExternalDataPoint.timestamp.asc())
        )
        return list(result.scalars().all())
