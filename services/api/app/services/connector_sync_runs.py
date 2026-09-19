"""Persist one connector sync attempt's outcome to `connector_sync_runs`.

Shared by both periodic pipelines that keep connector data current: the
generic `ExternalDataSyncScheduler` and the dedicated `NewsSyncScheduler`
(Marketaux's own shape, see `ConnectorMetadata.auto_synced`). The engine
is passed in rather than looked up here so each scheduler keeps resolving
`get_engine` through its own module, which is what its tests patch.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.external_data import ConnectorSyncRun
from app.repositories.connector_sync_runs import ConnectorSyncRunRepository

logger = logging.getLogger("app.services.connector_sync_runs")


def describe_failure(exc: BaseException) -> str:
    """A non-empty message for a failed attempt: `str(exc)`, or the
    exception's type name when its `str()` is blank (a bare
    `RuntimeError()` would otherwise record an empty, useless message)."""
    return str(exc) or type(exc).__name__


async def record_sync_run(
    engine: AsyncEngine | None,
    *,
    source: str,
    started_at: datetime,
    success: bool,
    received: int = 0,
    inserted: int = 0,
    updated: int = 0,
    duplicates_skipped: int = 0,
    rejected: int = 0,
    duration_seconds: float = 0.0,
    error_message: str | None = None,
) -> None:
    """Write one sync attempt's outcome.

    Best-effort, deliberately: a failure recording *health history* must
    never fail, or look like a failure of, the real ingestion it
    describes, so any error here is logged and swallowed.
    """
    if engine is None:
        return
    session = async_sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        await ConnectorSyncRunRepository(session).record(
            ConnectorSyncRun(
                source=source,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                success=success,
                received=received,
                inserted=inserted,
                updated=updated,
                duplicates_skipped=duplicates_skipped,
                rejected=rejected,
                duration_seconds=duration_seconds,
                error_message=error_message,
            )
        )
    except Exception:
        logger.exception("Failed to record sync run for %s", source)
    finally:
        await session.close()
