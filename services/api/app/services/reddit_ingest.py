"""Reddit ingestion — fetch real comments via `RedditConnector`, persist
them into `reddit_comments`, and mirror two *derived* daily aggregates
into `external_data_points`: comment volume (`reddit_volume`) and mean
VADER sentiment (`reddit_sentiment`).

Deliberately **not** `app.services.external_data_ingest`'s own generic
path — mirrors `app.services.news_ingest`'s own reasoning exactly: real
comments carry genuinely richer detail than a single `RawDataPoint`, and
a calendar day holds a variable, often-large number of them.
`RedditConnector` is registered `auto_synced=False` for exactly this
reason; `app.services.reddit_sync.RedditSyncScheduler` is the dedicated
periodic pipeline that calls this module instead.

Idempotent via `RedditComment.reddit_id`, already a genuine, source-
provided unique id (see that model's own docstring).
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

from app.connectors.reddit import (
    REDDIT_SENTIMENT_SOURCE,
    REDDIT_VOLUME_SOURCE,
    RedditConnector,
    RedditItem,
    score_comment,
)
from app.core.config import get_settings
from app.db.engine import get_engine
from app.models.external_data import ExternalDataPoint
from app.models.reddit import RedditComment
from app.repositories.external_data import ExternalDataRepository
from app.repositories.reddit import RedditRepository

logger = logging.getLogger("app.services.reddit_ingest")


class RedditFetcher(Protocol):
    """The only surface this module actually needs from a connector — a
    structural `Protocol`, mirroring `app.services.news_ingest.NewsFetcher`'s
    own reasoning, so a test double needs no inheritance from the real
    `RedditConnector` to stand in for one."""

    async def fetch_items(self, start: datetime, end: datetime) -> tuple[RedditItem, ...]: ...

    async def aclose(self) -> None: ...


class RedditIngestError(RuntimeError):
    """Raised when Reddit ingestion cannot proceed safely."""


@dataclass(frozen=True)
class RedditIngestReport:
    """Outcome of one Reddit ingestion run."""

    received: int
    inserted: int
    duplicates_skipped: int
    rejected: int
    #: Distinct calendar days whose own `reddit_volume`/`reddit_sentiment`
    #: aggregates were recomputed this run — 0 for a tick that received no
    #: new comments.
    days_recomputed: int
    duration_seconds: float


async def ingest_reddit(
    *,
    start: datetime,
    end: datetime,
    session: AsyncSession | None = None,
    connector: RedditFetcher | None = None,
) -> RedditIngestReport:
    """Fetch, validate, and persist real comments in `[start, end]`
    (inclusive both ends, this table's own established convention), then
    recompute and mirror every calendar day's own aggregates that this
    run's own comments touched.

    Args:
        start: Range start (inclusive, timezone-aware UTC).
        end: Range end (inclusive, timezone-aware UTC).
        session: Database session; built from the configured engine when
            omitted. Pass a session with no active transaction.
        connector: Injected for tests; a real `RedditConnector` when
            omitted.

    Raises:
        RedditIngestError: When the range is invalid or the database is
            not configured.
    """
    started_at = perf_counter()
    if start.tzinfo is None or end.tzinfo is None:
        raise RedditIngestError("start and end must be timezone-aware datetimes")
    if end < start:
        raise RedditIngestError("end must not be before start")

    logger.info("Reddit ingestion started (range=[%s, %s])", start.isoformat(), end.isoformat())

    owns_session = session is None
    if session is None:
        engine = get_engine()
        if engine is None:
            raise RedditIngestError("Database is not configured")
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()

    reddit_connector = connector or RedditConnector()
    try:
        items = await reddit_connector.fetch_items(start, end)
        inserted, duplicates_skipped, rejected = await _persist_items(session, items)
        days_recomputed = await _mirror_daily_aggregates(session, items)
    finally:
        await reddit_connector.aclose()
        if owns_session:
            await session.close()

    report = RedditIngestReport(
        received=len(items),
        inserted=inserted,
        duplicates_skipped=duplicates_skipped,
        rejected=rejected,
        days_recomputed=days_recomputed,
        duration_seconds=perf_counter() - started_at,
    )
    logger.info(
        "Reddit ingestion completed: received=%d inserted=%d duplicates_skipped=%d "
        "rejected=%d days_recomputed=%d in %.2fs",
        report.received,
        report.inserted,
        report.duplicates_skipped,
        report.rejected,
        report.days_recomputed,
        report.duration_seconds,
    )
    return report


async def _persist_items(
    session: AsyncSession, items: Sequence[RedditItem]
) -> tuple[int, int, int]:
    """Insert comments idempotently; return (inserted, duplicates_skipped, rejected).

    Mirrors `app.services.news_ingest._persist_articles`'s own shape:
    `reddit_id` is already a genuine unique id, so there is only ever one
    dedup key to check.
    """
    repository = RedditRepository(session)
    existing = await repository.get_existing_ids([item.reddit_id for item in items])

    pending: list[RedditComment] = []
    duplicates_skipped = 0
    for item in items:
        if item.reddit_id in existing:
            duplicates_skipped += 1
            continue
        pending.append(
            RedditComment(
                reddit_id=item.reddit_id,
                subreddit=item.subreddit,
                author=item.author,
                body=item.body,
                score=item.score,
                sentiment_score=score_comment(item.body),
                created_utc=item.created_utc,
                permalink=item.permalink,
                raw_payload=item.raw_payload,
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
                "Rejecting Reddit comment (reddit_id=%s): rejected by the database (%s)",
                row.reddit_id,
                exc.orig,
            )
    await session.commit()

    return inserted, duplicates_skipped, rejected


async def _mirror_daily_aggregates(session: AsyncSession, items: Sequence[RedditItem]) -> int:
    """Recompute and upsert `reddit_volume`/`reddit_sentiment` for every
    calendar day this run's own comments touched — not just newly-inserted
    ones, mirroring `app.services.news_ingest._mirror_daily_aggregates`'s
    own reasoning exactly (a duplicate-skipped comment still confirms that
    day already has real data; a genuinely new comment for an
    already-mirrored day is exactly the case this recompute must catch).

    Reads the *real, currently stored* `reddit_comments` rows for each
    touched day (never just this run's own batch), so the mirrored values
    always reflect everything known right now.
    """
    days = {item.created_utc.astimezone(UTC).date() for item in items}
    if not days:
        return 0

    external_data_repository = ExternalDataRepository(session)
    existing_volume = await external_data_repository.list_existing_values(
        REDDIT_VOLUME_SOURCE, None
    )
    existing_sentiment = await external_data_repository.list_existing_values(
        REDDIT_SENTIMENT_SOURCE, None
    )

    recomputed_days: set[datetime] = set()
    for day in sorted(days):
        day_start = datetime.combine(day, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)

        volume_result = await session.execute(
            select(func.count())
            .select_from(RedditComment)
            .where(
                RedditComment.created_utc >= day_start,
                RedditComment.created_utc < day_end,
            )
        )
        volume = float(volume_result.scalar_one())

        sentiment_result = await session.execute(
            select(func.avg(RedditComment.sentiment_score)).where(
                RedditComment.created_utc >= day_start,
                RedditComment.created_utc < day_end,
                RedditComment.sentiment_score.is_not(None),
            )
        )
        mean_sentiment = sentiment_result.scalar_one_or_none()

        volume_changed = await _upsert_aggregate(
            external_data_repository,
            source=REDDIT_VOLUME_SOURCE,
            day_start=day_start,
            value=volume,
            existing=existing_volume,
            raw_payload={"date": day.isoformat(), "comment_count": volume},
        )
        sentiment_changed = False
        if mean_sentiment is not None:
            sentiment_changed = await _upsert_aggregate(
                external_data_repository,
                source=REDDIT_SENTIMENT_SOURCE,
                day_start=day_start,
                value=float(mean_sentiment),
                existing=existing_sentiment,
                raw_payload={"date": day.isoformat(), "mean_sentiment": float(mean_sentiment)},
            )
        if volume_changed or sentiment_changed:
            recomputed_days.add(day_start)

    # `update_value` deliberately does not commit (see its own docstring)
    # — mirrors `news_ingest`'s own final commit after its analogous loop.
    await session.commit()

    return len(recomputed_days)


async def _upsert_aggregate(
    repository: ExternalDataRepository,
    *,
    source: str,
    day_start: datetime,
    value: float,
    existing: dict[datetime, float],
    raw_payload: dict[str, object],
) -> bool:
    """Create or revise one day's own aggregate point — both
    `reddit_volume` and `reddit_sentiment` behave like revisable values
    (a later-arriving comment for an already-mirrored day changes the
    real count/mean), the same reasoning `news_ingest`'s own
    `_mirror_daily_aggregates` already established for `news_sentiment`.

    Returns whether a real write happened (create, or an update whose
    value actually differs) — not merely that this day was *touched* this
    run, so a duplicate-only re-ingestion (same comments, same computed
    aggregate) is correctly reported as zero days recomputed, mirroring
    `news_ingest`'s own "duplicate skip, not a wasted write" discipline.
    """
    existing_value = existing.get(day_start)
    if existing_value is None:
        await repository.create(
            ExternalDataPoint(
                source=source,
                symbol=None,
                timestamp=day_start,
                value=value,
                raw_payload=raw_payload,
            )
        )
        return True
    if existing_value != value:
        await repository.update_value(source, None, day_start, value=value, raw_payload=raw_payload)
        return True
    return False


async def run_ingest_once(
    *, start: datetime | None = None, end: datetime | None = None
) -> RedditIngestReport:
    """Run one ingestion pass synchronously (CLI and manual verification).

    Defaults `end` to now and `start` to `reddit_sync_backfill_days` ago
    when omitted — mirrors `news_ingest.run_ingest_once`'s own role.
    """
    settings = get_settings()
    resolved_end = end if end is not None else datetime.now(UTC)
    resolved_start = (
        start
        if start is not None
        else resolved_end - timedelta(days=settings.reddit_sync_backfill_days)
    )
    return await ingest_reddit(start=resolved_start, end=resolved_end)
