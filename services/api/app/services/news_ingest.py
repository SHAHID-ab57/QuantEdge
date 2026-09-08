"""News ingestion — fetch real articles via `MarketauxConnector`, persist
them into `news_articles`, and mirror a *derived* daily mean sentiment
into `external_data_points` (source `news_sentiment`).

Deliberately **not** `app.services.external_data_ingest`'s own generic
path: that pipeline assumes one connector, one numeric `RawDataPoint` per
call, persisted straight into `external_data_points` — real articles
carry genuinely richer detail (see `app.models.news.NewsArticle`'s own
module docstring), and a single calendar day can hold zero, one, or many
of them, which a bare "fetch a point, persist it" tick has no way to
express at all. `MarketauxConnector` is registered
`auto_synced=False` for exactly this reason (see `ConnectorMetadata
.auto_synced`'s own docstring) — `ExternalDataSyncScheduler`'s own
generic tick never touches this source; `app.services.news_sync
.NewsSyncScheduler` is the dedicated periodic pipeline that calls this
module instead.

Idempotent the same way every other connector's ingestion is, but via a
simpler mechanism: `NewsArticle.marketaux_uuid` is already a genuine,
source-provided unique id (see that model's own docstring for why this
needs no `(source, symbol, timestamp)`-style compound check at all).
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from time import perf_counter
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.connectors.marketaux import MARKETAUX_SOURCE, MarketauxArticle, MarketauxConnector
from app.core.config import get_settings
from app.db.engine import get_engine
from app.models.external_data import ExternalDataPoint
from app.models.news import NewsArticle
from app.repositories.external_data import ExternalDataRepository
from app.repositories.news import NewsRepository

logger = logging.getLogger("app.services.news_ingest")


class NewsFetcher(Protocol):
    """The only surface this module actually needs from a connector —
    a structural `Protocol`, mirroring `app.connectors.base.Connector`'s
    own reasoning, so a test double needs no inheritance from the real
    `MarketauxConnector` to stand in for one."""

    async def fetch_articles(
        self, start: datetime, end: datetime
    ) -> tuple[MarketauxArticle, ...]: ...

    async def aclose(self) -> None: ...


class NewsIngestError(RuntimeError):
    """Raised when news ingestion cannot proceed safely."""


@dataclass(frozen=True)
class NewsIngestReport:
    """Outcome of one news ingestion run."""

    received: int
    inserted: int
    duplicates_skipped: int
    rejected: int
    #: Distinct calendar days whose own `news_sentiment` aggregate was
    #: recomputed this run — 0 for a tick that received no new articles.
    days_recomputed: int
    duration_seconds: float


async def ingest_news(
    *,
    start: datetime,
    end: datetime,
    session: AsyncSession | None = None,
    connector: NewsFetcher | None = None,
) -> NewsIngestReport:
    """Fetch, validate, and persist real articles in `[start, end]`
    (inclusive both ends, this table's own established convention), then
    recompute and mirror every calendar day's own aggregate that this
    run's own articles touched.

    Args:
        start: Range start (inclusive, timezone-aware UTC).
        end: Range end (inclusive, timezone-aware UTC).
        session: Database session; built from the configured engine when
            omitted. Pass a session with no active transaction.
        connector: Injected for tests; a real `MarketauxConnector` when
            omitted.

    Raises:
        NewsIngestError: When the range is invalid or the database is
            not configured.
    """
    started_at = perf_counter()
    if start.tzinfo is None or end.tzinfo is None:
        raise NewsIngestError("start and end must be timezone-aware datetimes")
    if end < start:
        raise NewsIngestError("end must not be before start")

    logger.info("News ingestion started (range=[%s, %s])", start.isoformat(), end.isoformat())

    owns_session = session is None
    if session is None:
        engine = get_engine()
        if engine is None:
            raise NewsIngestError("Database is not configured")
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()

    news_connector = connector or MarketauxConnector()
    try:
        articles = await news_connector.fetch_articles(start, end)
        inserted, duplicates_skipped, rejected = await _persist_articles(session, articles)
        days_recomputed = await _mirror_daily_aggregates(session, articles)
    finally:
        await news_connector.aclose()
        if owns_session:
            await session.close()

    report = NewsIngestReport(
        received=len(articles),
        inserted=inserted,
        duplicates_skipped=duplicates_skipped,
        rejected=rejected,
        days_recomputed=days_recomputed,
        duration_seconds=perf_counter() - started_at,
    )
    logger.info(
        "News ingestion completed: received=%d inserted=%d duplicates_skipped=%d "
        "rejected=%d days_recomputed=%d in %.2fs",
        report.received,
        report.inserted,
        report.duplicates_skipped,
        report.rejected,
        report.days_recomputed,
        report.duration_seconds,
    )
    return report


async def _persist_articles(
    session: AsyncSession, articles: Sequence[MarketauxArticle]
) -> tuple[int, int, int]:
    """Insert articles idempotently; return (inserted, duplicates_skipped, rejected).

    Mirrors `app.services.external_data_ingest._persist_points`'s own
    shape, simplified: `marketaux_uuid` is already a genuine unique id, so
    there is only ever one dedup key to check, never a per-symbol split.
    """
    repository = NewsRepository(session)
    existing = await repository.get_existing_uuids([a.marketaux_uuid for a in articles])

    pending: list[NewsArticle] = []
    duplicates_skipped = 0
    for article in articles:
        if article.marketaux_uuid in existing:
            duplicates_skipped += 1
            continue
        pending.append(
            NewsArticle(
                marketaux_uuid=article.marketaux_uuid,
                headline=article.headline,
                snippet=article.snippet,
                source=article.source,
                url=article.url,
                published_at=article.published_at,
                sentiment_score=article.sentiment_score,
                primary_symbol=article.symbols[0] if article.symbols else None,
                symbols=list(article.symbols),
                raw_payload=article.raw_payload,
            )
        )

    if not pending:
        return 0, duplicates_skipped, 0

    inserted = 0
    rejected = 0
    for row in pending:
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            inserted += 1
        except IntegrityError as exc:
            rejected += 1
            logger.warning(
                "Rejecting news article (marketaux_uuid=%s): rejected by the database (%s)",
                row.marketaux_uuid,
                exc.orig,
            )
    await session.commit()

    return inserted, duplicates_skipped, rejected


async def _mirror_daily_aggregates(
    session: AsyncSession, articles: Sequence[MarketauxArticle]
) -> int:
    """Recompute and upsert `news_sentiment` for every calendar day this
    run's own articles touched — not just newly-inserted ones: a
    duplicate-skipped article still confirms that day already has real
    data, and a genuinely *new* article for an already-mirrored day is
    exactly the case this recompute must catch (see this module's own
    docstring on why `news_sentiment` behaves like a revisable value,
    the same reasoning DefiLlama's own `revisable=True` already
    established, applied here directly rather than through that shared
    flag — this path never goes through `_persist_points` at all).

    Reads the *real, currently stored* `news_articles` rows for each
    touched day (never just this run's own batch) so the mirrored value
    always reflects everything known right now, not only what this one
    tick happened to fetch.
    """
    days = {article.published_at.astimezone(UTC).date() for article in articles}
    if not days:
        return 0

    external_data_repository = ExternalDataRepository(session)
    existing_values = await external_data_repository.list_existing_values(MARKETAUX_SOURCE, None)

    recomputed = 0
    for day in sorted(days):
        day_start = datetime.combine(day, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        mean_result = await session.execute(
            select(func.avg(NewsArticle.sentiment_score)).where(
                NewsArticle.published_at >= day_start,
                NewsArticle.published_at < day_end,
                NewsArticle.sentiment_score.is_not(None),
            )
        )
        mean_sentiment = mean_result.scalar_one_or_none()
        if mean_sentiment is None:
            continue

        mean_sentiment = float(mean_sentiment)
        raw_payload = {"date": day.isoformat(), "mean_sentiment": mean_sentiment}
        existing_value = existing_values.get(day_start)
        if existing_value is None:
            await external_data_repository.create(
                ExternalDataPoint(
                    source=MARKETAUX_SOURCE,
                    symbol=None,
                    timestamp=day_start,
                    value=mean_sentiment,
                    raw_payload=raw_payload,
                )
            )
            recomputed += 1
        elif existing_value != mean_sentiment:
            await external_data_repository.update_value(
                MARKETAUX_SOURCE, None, day_start, value=mean_sentiment, raw_payload=raw_payload
            )
            recomputed += 1

    # `update_value` deliberately does not commit (see its own
    # docstring) — mirrors `_persist_points`'s own final commit after its
    # analogous `update_value` loop, covering every revision made above.
    await session.commit()

    return recomputed


async def run_ingest_once(
    *, start: datetime | None = None, end: datetime | None = None
) -> NewsIngestReport:
    """Run one ingestion pass synchronously (CLI and manual verification).

    Defaults `end` to now and `start` to `news_sync_backfill_days` ago
    when omitted — mirrors `external_data_ingest.run_ingest_once`'s own
    role for the generic connectors.
    """
    settings = get_settings()
    resolved_end = end if end is not None else datetime.now(UTC)
    resolved_start = (
        start
        if start is not None
        else resolved_end - timedelta(days=settings.news_sync_backfill_days)
    )
    return await ingest_news(start=resolved_start, end=resolved_end)
