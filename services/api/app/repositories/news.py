"""News article storage access — mirrors
`app.repositories.external_data.ExternalDataRepository`'s own shape,
adapted for `NewsArticle`'s own real idempotency key (`marketaux_uuid`,
already genuinely unique — no `(source, symbol, timestamp)`-style
compound check needed, see that model's own docstring for why).
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsArticle


class NewsRepository:
    """Create/read access to `news_articles`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, article: NewsArticle) -> NewsArticle:
        self.session.add(article)
        await self.session.commit()
        await self.session.refresh(article)
        return article

    async def get_existing_uuids(self, marketaux_uuids: list[str]) -> set[str]:
        """Which of these Marketaux uuids are already stored — the real
        idempotency check `app.services.news_ingest` runs before every
        insert, mirroring `ExternalDataRepository
        .list_existing_timestamps`'s own pre-insert-check role."""
        if not marketaux_uuids:
            return set()
        result = await self.session.execute(
            select(NewsArticle.marketaux_uuid).where(
                NewsArticle.marketaux_uuid.in_(marketaux_uuids)
            )
        )
        return set(result.scalars())

    async def list_paginated(
        self,
        *,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int,
        offset: int,
    ) -> list[NewsArticle]:
        """A page of articles, newest first (a reader wants the latest
        headlines first — unlike `ExternalDataPoint`'s own oldest-first
        convention, which exists for `most_recent_value_at_or_before`'s
        own bisect search; nothing here needs that ordering). `start`/
        `end` filter on `published_at`, inclusive both ends, mirroring
        this platform's own established external-data range convention.
        """
        query = (
            select(NewsArticle)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if symbol is not None:
            query = query.where(NewsArticle.primary_symbol == symbol)
        if start is not None:
            query = query.where(NewsArticle.published_at >= start)
        if end is not None:
            query = query.where(NewsArticle.published_at <= end)
        return list((await self.session.execute(query)).scalars())

    async def count(
        self,
        *,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Total articles matching the same filter `list_paginated`
        applies, ignoring `limit`/`offset` — the listing endpoint's page
        total."""
        query = select(func.count()).select_from(NewsArticle)
        if symbol is not None:
            query = query.where(NewsArticle.primary_symbol == symbol)
        if start is not None:
            query = query.where(NewsArticle.published_at >= start)
        if end is not None:
            query = query.where(NewsArticle.published_at <= end)
        return (await self.session.execute(query)).scalar_one()

    async def get_latest_published_at(self) -> datetime | None:
        """The newest stored article's own `published_at`, or `None` if
        nothing has been ingested yet — `NewsSyncScheduler`'s own
        "resume from here" anchor (with a deliberate safety margin; see
        that module's own docstring for why it isn't used as a bare
        floor)."""
        result = await self.session.execute(select(func.max(NewsArticle.published_at)))
        return result.scalar_one_or_none()
