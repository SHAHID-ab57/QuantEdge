"""Tests for `app.services.news_ingest` — mirrors
`tests/services/test_external_data_ingest.py`'s own shape: a fake
connector stands in for the real network call, persistence is exercised
against the real in-memory SQLite session. Genuinely new coverage this
module needs that the generic ingestion tests don't: the daily aggregate
computation and its own revisable-like recompute behavior (see
`app.services.news_ingest._mirror_daily_aggregates`'s own docstring).

Every session this file opens is closed explicitly via `async with` —
including the one passed into `ingest_news` itself — rather than left to
garbage collection: an unclosed `AsyncSession` left for the GC to finalize
whenever it gets around to it is exactly the kind of thing that can
surface as a spurious "no such table" failure once thousands of other
tests are also allocating and disposing their own in-memory engines in
the same process.
"""

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from sqlalchemy import func, select

from app.connectors.marketaux import MARKETAUX_SOURCE, MarketauxArticle
from app.models.external_data import ExternalDataPoint
from app.models.news import NewsArticle
from app.services.news_ingest import NewsIngestError, NewsIngestReport, ingest_news
from tests.conftest import SessionFactory

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def article(
    *,
    uuid: str,
    published_at: datetime,
    sentiment_score: float | None,
    symbols: tuple[str, ...] = ("ETHUSD",),
) -> MarketauxArticle:
    return MarketauxArticle(
        marketaux_uuid=uuid,
        headline=f"Headline {uuid}",
        snippet="A snippet.",
        source="example.com",
        url=f"https://example.com/{uuid}",
        published_at=published_at,
        sentiment_score=sentiment_score,
        symbols=symbols,
        raw_payload={"uuid": uuid},
    )


class FakeMarketauxConnector:
    """A controllable stand-in for `MarketauxConnector` — returns
    whatever `articles` were configured. Class-level state (reset by the
    `reset_fake_connector` fixture) since real ingestion builds one per
    call, mirroring the real contract."""

    articles: ClassVar[tuple[MarketauxArticle, ...]] = ()
    aclose_calls: ClassVar[int] = 0

    async def fetch_articles(self, start: datetime, end: datetime) -> tuple[MarketauxArticle, ...]:
        return FakeMarketauxConnector.articles

    async def aclose(self) -> None:
        FakeMarketauxConnector.aclose_calls += 1


@pytest.fixture(autouse=True)
def reset_fake_connector():
    FakeMarketauxConnector.articles = ()
    FakeMarketauxConnector.aclose_calls = 0
    yield


async def run_ingest(
    session_factory: SessionFactory, *, start: datetime, end: datetime
) -> NewsIngestReport:
    """Run one `ingest_news` pass with an explicitly, promptly closed
    session — see this module's own docstring for why."""
    async with session_factory() as session:
        return await ingest_news(
            start=start, end=end, session=session, connector=FakeMarketauxConnector()
        )


async def count_articles(session_factory: SessionFactory) -> int:
    async with session_factory() as session:
        return (await session.execute(select(func.count()).select_from(NewsArticle))).scalar_one()


async def get_mirrored_value(session_factory: SessionFactory, timestamp: datetime) -> float | None:
    async with session_factory() as session:
        result = await session.execute(
            select(ExternalDataPoint.value).where(
                ExternalDataPoint.source == MARKETAUX_SOURCE,
                ExternalDataPoint.timestamp == timestamp,
            )
        )
        return result.scalar_one_or_none()


@pytest.mark.asyncio
class TestIngestNews:
    async def test_fetches_and_persists_every_article(
        self, session_factory: SessionFactory
    ) -> None:
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=0.5),
            article(uuid="a2", published_at=BASE + timedelta(hours=1), sentiment_score=-0.2),
        )

        report = await run_ingest(session_factory, start=BASE, end=BASE + timedelta(days=1))

        assert report.received == 2
        assert report.inserted == 2
        assert report.duplicates_skipped == 0
        assert report.rejected == 0
        assert await count_articles(session_factory) == 2
        assert FakeMarketauxConnector.aclose_calls == 1

    async def test_duplicate_articles_are_skipped_idempotently(
        self, session_factory: SessionFactory
    ) -> None:
        """Re-ingesting the same range inserts nothing the second time —
        `marketaux_uuid` is a genuine, source-provided unique id, no
        timestamp-based dedup heuristic needed."""
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=0.5),
        )

        first = await run_ingest(session_factory, start=BASE, end=BASE)
        second = await run_ingest(session_factory, start=BASE, end=BASE)

        assert first.inserted == 1
        assert second.inserted == 0
        assert second.duplicates_skipped == 1
        assert await count_articles(session_factory) == 1

    async def test_naive_datetimes_are_rejected_before_any_fetch(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(NewsIngestError, match="timezone-aware"):
            await run_ingest(session_factory, start=BASE.replace(tzinfo=None), end=BASE)

    async def test_end_before_start_is_rejected(self, session_factory: SessionFactory) -> None:
        with pytest.raises(NewsIngestError, match="end must not be before start"):
            await run_ingest(session_factory, start=BASE, end=BASE - timedelta(days=1))

    async def test_database_not_configured_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.news_ingest as news_ingest_module

        monkeypatch.setattr(news_ingest_module, "get_engine", lambda: None)
        with pytest.raises(NewsIngestError, match="Database is not configured"):
            await ingest_news(start=BASE, end=BASE, connector=FakeMarketauxConnector())


@pytest.mark.asyncio
class TestDailyAggregateMirroring:
    async def test_a_single_article_day_mirrors_its_own_sentiment(
        self, session_factory: SessionFactory
    ) -> None:
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=0.5),
        )

        report = await run_ingest(session_factory, start=BASE, end=BASE)

        assert report.days_recomputed == 1
        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, day_start) == pytest.approx(0.5)

    async def test_multiple_articles_the_same_day_mirror_the_mean(
        self, session_factory: SessionFactory
    ) -> None:
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=0.6),
            article(uuid="a2", published_at=BASE + timedelta(hours=2), sentiment_score=0.2),
        )

        await run_ingest(session_factory, start=BASE, end=BASE + timedelta(hours=3))

        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, day_start) == pytest.approx(0.4)

    async def test_a_day_with_no_scored_articles_is_not_mirrored(
        self, session_factory: SessionFactory
    ) -> None:
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=None),
        )

        report = await run_ingest(session_factory, start=BASE, end=BASE)

        assert report.days_recomputed == 0
        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, day_start) is None

    async def test_a_late_arriving_article_recomputes_an_already_mirrored_day(
        self, session_factory: SessionFactory
    ) -> None:
        """The load-bearing proof of this design's own revisable-like
        behavior: a genuinely new article for a day already mirrored
        changes that day's own stored aggregate — the same "a dataset
        built after the fact reflects it" contract DefiLlama's own
        `revisable=True` already established, applied here directly."""
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=0.6),
        )
        await run_ingest(session_factory, start=BASE, end=BASE)
        day_start = datetime(2026, 1, 1, tzinfo=UTC)
        assert await get_mirrored_value(session_factory, day_start) == pytest.approx(0.6)

        # A second, real article for the *same calendar day*, discovered
        # on a later tick.
        FakeMarketauxConnector.articles = (
            article(uuid="a2", published_at=BASE + timedelta(hours=5), sentiment_score=0.0),
        )
        second_report = await run_ingest(
            session_factory, start=BASE + timedelta(hours=4), end=BASE + timedelta(hours=6)
        )

        assert second_report.days_recomputed == 1
        assert await get_mirrored_value(session_factory, day_start) == pytest.approx(0.3)

    async def test_a_second_tick_with_nothing_new_for_that_day_does_not_rewrite_it(
        self, session_factory: SessionFactory
    ) -> None:
        """Not "always rewrite" — an unchanged mean is left alone, the
        same "duplicate skip, not a wasted write" discipline DefiLlama's
        own `revisable=True` path already established."""
        FakeMarketauxConnector.articles = (
            article(uuid="a1", published_at=BASE, sentiment_score=0.6),
        )
        await run_ingest(session_factory, start=BASE, end=BASE)

        # Same article re-fetched (e.g. a re-run over an overlapping
        # window) — duplicate-skipped, and the mean is unchanged.
        second_report = await run_ingest(session_factory, start=BASE, end=BASE)

        assert second_report.duplicates_skipped == 1
        assert second_report.days_recomputed == 0
