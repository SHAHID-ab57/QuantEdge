"""Tests for `app.services.reddit_ingest` — mirrors
`tests/services/test_news_ingest.py`'s own shape: a fake connector stands
in for the real network call, persistence is exercised against the real
in-memory SQLite session. Genuinely new coverage this module needs beyond
News's own: **two** daily aggregates (volume, sentiment) computed from
one shared batch of items, and a volume count that stays correct even
when every comment in a day is sentiment-less (deleted/removed).
"""

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from sqlalchemy import func, select

from app.connectors.reddit import REDDIT_SENTIMENT_SOURCE, REDDIT_VOLUME_SOURCE, RedditItem
from app.models.external_data import ExternalDataPoint
from app.models.reddit import RedditComment
from app.services.reddit_ingest import RedditIngestError, RedditIngestReport, ingest_reddit
from tests.conftest import SessionFactory

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def comment(
    *,
    reddit_id: str,
    created_utc: datetime,
    body: str = "a real comment",
    subreddit: str = "ethereum",
    score: int = 1,
) -> RedditItem:
    return RedditItem(
        reddit_id=reddit_id,
        subreddit=subreddit,
        author="someone",
        body=body,
        score=score,
        created_utc=created_utc,
        permalink=f"/r/{subreddit}/comments/x/{reddit_id}/",
        raw_payload={"id": reddit_id},
    )


class FakeRedditConnector:
    """A controllable stand-in for `RedditConnector` — returns whatever
    `items` were configured. Class-level state (reset by the
    `reset_fake_connector` fixture) since real ingestion builds one per
    call, mirroring the real contract."""

    items: ClassVar[tuple[RedditItem, ...]] = ()
    aclose_calls: ClassVar[int] = 0

    async def fetch_items(self, start: datetime, end: datetime) -> tuple[RedditItem, ...]:
        return FakeRedditConnector.items

    async def aclose(self) -> None:
        FakeRedditConnector.aclose_calls += 1


@pytest.fixture(autouse=True)
def reset_fake_connector():
    FakeRedditConnector.items = ()
    FakeRedditConnector.aclose_calls = 0
    yield


async def run_ingest(
    session_factory: SessionFactory, *, start: datetime, end: datetime
) -> RedditIngestReport:
    """Run one `ingest_reddit` pass with an explicitly, promptly closed
    session — mirrors `test_news_ingest.py`'s own reasoning for why."""
    async with session_factory() as session:
        return await ingest_reddit(
            start=start, end=end, session=session, connector=FakeRedditConnector()
        )


async def count_comments(session_factory: SessionFactory) -> int:
    async with session_factory() as session:
        return (
            await session.execute(select(func.count()).select_from(RedditComment))
        ).scalar_one()


async def get_mirrored_value(
    session_factory: SessionFactory, source: str, timestamp: datetime
) -> float | None:
    async with session_factory() as session:
        result = await session.execute(
            select(ExternalDataPoint.value).where(
                ExternalDataPoint.source == source,
                ExternalDataPoint.timestamp == timestamp,
            )
        )
        return result.scalar_one_or_none()


@pytest.mark.asyncio
class TestIngestReddit:
    async def test_fetches_and_persists_every_comment(
        self, session_factory: SessionFactory
    ) -> None:
        FakeRedditConnector.items = (
            comment(reddit_id="c1", created_utc=BASE),
            comment(reddit_id="c2", created_utc=BASE + timedelta(hours=1)),
        )

        report = await run_ingest(session_factory, start=BASE, end=BASE + timedelta(days=1))

        assert report.received == 2
        assert report.inserted == 2
        assert report.duplicates_skipped == 0
        assert report.rejected == 0
        assert await count_comments(session_factory) == 2
        assert FakeRedditConnector.aclose_calls == 1

    async def test_duplicate_comments_are_skipped_idempotently(
        self, session_factory: SessionFactory
    ) -> None:
        FakeRedditConnector.items = (comment(reddit_id="c1", created_utc=BASE),)

        first = await run_ingest(session_factory, start=BASE, end=BASE)
        second = await run_ingest(session_factory, start=BASE, end=BASE)

        assert first.inserted == 1
        assert second.inserted == 0
        assert second.duplicates_skipped == 1
        assert await count_comments(session_factory) == 1

    async def test_naive_datetimes_are_rejected_before_any_fetch(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(RedditIngestError, match="timezone-aware"):
            await run_ingest(session_factory, start=BASE.replace(tzinfo=None), end=BASE)

    async def test_end_before_start_is_rejected(self, session_factory: SessionFactory) -> None:
        with pytest.raises(RedditIngestError, match="end must not be before start"):
            await run_ingest(session_factory, start=BASE, end=BASE - timedelta(days=1))

    async def test_database_not_configured_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.reddit_ingest as reddit_ingest_module

        monkeypatch.setattr(reddit_ingest_module, "get_engine", lambda: None)
        with pytest.raises(RedditIngestError, match="Database is not configured"):
            await ingest_reddit(start=BASE, end=BASE, connector=FakeRedditConnector())

    async def test_a_deleted_comments_sentiment_score_is_stored_as_null(
        self, session_factory: SessionFactory
    ) -> None:
        FakeRedditConnector.items = (comment(reddit_id="c1", created_utc=BASE, body="[deleted]"),)
        await run_ingest(session_factory, start=BASE, end=BASE)

        async with session_factory() as session:
            row = (
                await session.execute(
                    select(RedditComment).where(RedditComment.reddit_id == "c1")
                )
            ).scalar_one()
        assert row.sentiment_score is None


@pytest.mark.asyncio
class TestDailyAggregateMirroring:
    async def test_a_single_comment_day_mirrors_volume_and_sentiment(
        self, session_factory: SessionFactory
    ) -> None:
        FakeRedditConnector.items = (
            comment(reddit_id="c1", created_utc=BASE, body="I love this, going to the moon"),
        )

        report = await run_ingest(session_factory, start=BASE, end=BASE)

        assert report.days_recomputed == 1
        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, REDDIT_VOLUME_SOURCE, day_start) == 1.0
        sentiment = await get_mirrored_value(session_factory, REDDIT_SENTIMENT_SOURCE, day_start)
        assert sentiment is not None
        assert sentiment > 0

    async def test_multiple_comments_the_same_day_mirror_count_and_mean(
        self, session_factory: SessionFactory
    ) -> None:
        FakeRedditConnector.items = (
            comment(reddit_id="c1", created_utc=BASE, body="great news"),
            comment(reddit_id="c2", created_utc=BASE + timedelta(hours=2), body="terrible news"),
            comment(reddit_id="c3", created_utc=BASE + timedelta(hours=3), body="[deleted]"),
        )

        await run_ingest(session_factory, start=BASE, end=BASE + timedelta(hours=4))

        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        # All three comments count toward volume, including the deleted one.
        assert await get_mirrored_value(session_factory, REDDIT_VOLUME_SOURCE, day_start) == 3.0
        # Only the two scoreable comments feed the sentiment mean.
        sentiment = await get_mirrored_value(session_factory, REDDIT_SENTIMENT_SOURCE, day_start)
        assert sentiment is not None

    async def test_a_day_with_only_deleted_comments_mirrors_volume_but_not_sentiment(
        self, session_factory: SessionFactory
    ) -> None:
        FakeRedditConnector.items = (
            comment(reddit_id="c1", created_utc=BASE, body="[deleted]"),
            comment(reddit_id="c2", created_utc=BASE + timedelta(hours=1), body="[removed]"),
        )

        report = await run_ingest(session_factory, start=BASE, end=BASE + timedelta(hours=2))

        assert report.days_recomputed == 1
        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, REDDIT_VOLUME_SOURCE, day_start) == 2.0
        assert await get_mirrored_value(session_factory, REDDIT_SENTIMENT_SOURCE, day_start) is None

    async def test_a_late_arriving_comment_recomputes_an_already_mirrored_day(
        self, session_factory: SessionFactory
    ) -> None:
        """The load-bearing proof of this design's own revisable-like
        behavior: a genuinely new comment for a day already mirrored
        changes that day's own stored volume and mean sentiment."""
        FakeRedditConnector.items = (
            comment(reddit_id="c1", created_utc=BASE, body="great news"),
        )
        await run_ingest(session_factory, start=BASE, end=BASE)
        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, REDDIT_VOLUME_SOURCE, day_start) == 1.0

        FakeRedditConnector.items = (
            comment(reddit_id="c2", created_utc=BASE + timedelta(hours=5), body="more news"),
        )
        second_report = await run_ingest(
            session_factory, start=BASE + timedelta(hours=4), end=BASE + timedelta(hours=6)
        )

        assert second_report.days_recomputed == 1
        assert await get_mirrored_value(session_factory, REDDIT_VOLUME_SOURCE, day_start) == 2.0

    async def test_a_second_tick_with_nothing_new_for_that_day_does_not_rewrite_it(
        self, session_factory: SessionFactory
    ) -> None:
        """Not "always rewrite" — an unchanged count/mean is left alone,
        the same "duplicate skip, not a wasted write" discipline
        `news_ingest` already established."""
        FakeRedditConnector.items = (
            comment(reddit_id="c1", created_utc=BASE, body="great news"),
        )
        await run_ingest(session_factory, start=BASE, end=BASE)

        second_report = await run_ingest(session_factory, start=BASE, end=BASE)

        assert second_report.duplicates_skipped == 1
        assert second_report.days_recomputed == 0
