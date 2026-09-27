"""Reddit comment storage access — mirrors `app.repositories.news
.NewsRepository`'s own shape, adapted for `RedditComment`'s own real
idempotency key (`reddit_id`, already genuinely unique — no
`(source, symbol, timestamp)`-style compound check needed).
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reddit import RedditComment


class RedditRepository:
    """Create/read access to `reddit_comments`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_existing_ids(self, reddit_ids: list[str]) -> set[str]:
        """Which of these Reddit comment ids are already stored — the
        real idempotency check `app.services.reddit_ingest` runs before
        every insert."""
        if not reddit_ids:
            return set()
        result = await self.session.execute(
            select(RedditComment.reddit_id).where(RedditComment.reddit_id.in_(reddit_ids))
        )
        return set(result.scalars())

    async def list_paginated(
        self,
        *,
        subreddit: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int,
        offset: int,
    ) -> list[RedditComment]:
        """A page of comments, newest first — mirrors `NewsRepository
        .list_paginated`'s own ordering reasoning exactly."""
        query = (
            select(RedditComment)
            .order_by(RedditComment.created_utc.desc())
            .limit(limit)
            .offset(offset)
        )
        if subreddit is not None:
            query = query.where(RedditComment.subreddit == subreddit)
        if start is not None:
            query = query.where(RedditComment.created_utc >= start)
        if end is not None:
            query = query.where(RedditComment.created_utc <= end)
        return list((await self.session.execute(query)).scalars())

    async def count(
        self,
        *,
        subreddit: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Total comments matching the same filter `list_paginated`
        applies, ignoring `limit`/`offset` — the listing endpoint's page
        total."""
        query = select(func.count()).select_from(RedditComment)
        if subreddit is not None:
            query = query.where(RedditComment.subreddit == subreddit)
        if start is not None:
            query = query.where(RedditComment.created_utc >= start)
        if end is not None:
            query = query.where(RedditComment.created_utc <= end)
        return (await self.session.execute(query)).scalar_one()

    async def get_latest_created_utc(self) -> datetime | None:
        """The newest stored comment's own `created_utc`, or `None` if
        nothing has been ingested yet — `RedditSyncScheduler`'s own
        "resume from here" anchor."""
        result = await self.session.execute(select(func.max(RedditComment.created_utc)))
        return result.scalar_one_or_none()
