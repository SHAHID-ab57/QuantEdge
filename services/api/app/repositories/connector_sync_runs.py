"""`connector_sync_runs` storage access — one repository per table, mirroring
`app.repositories.external_data.ExternalDataRepository`'s own split.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_data import ConnectorSyncRun


class ConnectorSyncRunRepository:
    """Create/read access to `connector_sync_runs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, run: ConnectorSyncRun) -> ConnectorSyncRun:
        """Persist one sync attempt's outcome. Commits on its own — this
        table is an audit trail of what already happened, never part of
        the same transaction as the ingestion it describes (ingestion has
        already committed or failed by the time this is called)."""
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def list_recent(self, source: str, *, limit: int = 20) -> list[ConnectorSyncRun]:
        """This source's most recent sync attempts, newest first."""
        result = await self.session.execute(
            select(ConnectorSyncRun)
            .where(ConnectorSyncRun.source == source)
            .order_by(ConnectorSyncRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars())
