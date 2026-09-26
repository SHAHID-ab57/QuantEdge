"""Business logic for the External Data Connectors read API — the Data
Sources page's (M4-E1-T3) own backend, distinct from ingestion
(`app.services.external_data_ingest`/`external_data_sync`): this module
only ever reads, mirroring `app.services.features.FeatureService`'s own
"reads straight from the registry" role for `/features`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.connectors import load_builtin_connectors
from app.connectors.errors import ConnectorSourceNotFoundError
from app.connectors.health import FAILING_STREAK, compute_health_status
from app.connectors.registry import default_registry as default_connector_registry
from app.core.config import get_settings
from app.repositories.connector_sync_runs import ConnectorSyncRunRepository
from app.repositories.external_data import ExternalDataRepository
from app.schemas.connectors import (
    ConnectorCatalogResponse,
    ConnectorDTO,
    ConnectorHistoryPagination,
    ConnectorHistoryResponse,
    ExternalDataPointDTO,
)

#: Every connector registered today reports a source-wide value, never a
#: per-market one (`RawDataPoint.symbol` is `None` for Fear & Greed) — this
#: service reads that same fixed symbol. A future per-symbol connector
#: would need a `symbol` query parameter threaded through both endpoints;
#: not built ahead of a real need for it.
_GLOBAL_SYMBOL = None

DEFAULT_HISTORY_LIMIT = 100
MAX_HISTORY_LIMIT = 1000


@dataclass
class ConnectorService:
    """Business logic for `GET /connectors` and `GET /connectors/{source}/history`."""

    external_data_repository: ExternalDataRepository
    sync_run_repository: ConnectorSyncRunRepository

    async def list_connectors(self) -> ConnectorCatalogResponse:
        """Every registered connector, each with its own most recent value.

        Reads straight from `ConnectorRegistry`, so a connector added to
        `app/connectors/` appears here with no change to this service —
        the same guarantee `FeatureService.list_features` gives `/features`.
        A connector with no ingested points yet (registered but never
        synced) reports `latest_value`/`latest_timestamp` as `null`, never
        a crash or a fabricated value.
        """
        load_builtin_connectors()
        settings = get_settings()
        now = datetime.now(UTC)
        entries = []
        for metadata in default_connector_registry.describe_all():
            latest = await self.external_data_repository.get_latest(metadata.source, _GLOBAL_SYMBOL)
            latest_timestamp = latest.timestamp if latest is not None else None
            total_points = await self.external_data_repository.count(
                metadata.source, _GLOBAL_SYMBOL
            )
            # `list_recent` is already newest-first and already fetched for the
            # failure-streak check below — its first row, if any, *is* the most
            # recent sync attempt on record, so no second query is needed to know
            # "when did the owning scheduler last actually try this source."
            recent_runs = await self.sync_run_repository.list_recent(
                metadata.source, limit=FAILING_STREAK
            )
            last_attempt = recent_runs[0] if recent_runs else None
            # A source with `auto_synced=False` (today, only Marketaux) is kept
            # current by `NewsSyncScheduler` on its own interval, never the
            # generic `ExternalDataSyncScheduler` — the interval used to project
            # `next_sync_at` has to match whichever one actually owns it, or the
            # estimate would be wrong for exactly the one source that needs a
            # different number.
            interval_seconds = (
                settings.external_data_sync_interval_seconds
                if metadata.auto_synced
                else settings.news_sync_interval_seconds
            )
            next_sync_at = (
                last_attempt.started_at + timedelta(seconds=interval_seconds)
                if last_attempt is not None
                else None
            )
            entries.append(
                ConnectorDTO(
                    source=metadata.source,
                    label=metadata.label,
                    description=metadata.description,
                    frequency=metadata.frequency,
                    requires_auth=metadata.requires_auth,
                    latest_value=latest.value if latest is not None else None,
                    latest_timestamp=latest_timestamp,
                    expected_interval_seconds=metadata.expected_interval_seconds,
                    total_points=total_points,
                    last_attempt_at=last_attempt.started_at if last_attempt is not None else None,
                    last_attempt_success=(
                        last_attempt.success if last_attempt is not None else None
                    ),
                    next_sync_at=next_sync_at,
                    health_status=compute_health_status(
                        latest_timestamp=latest_timestamp,
                        expected_interval_seconds=metadata.expected_interval_seconds,
                        now=now,
                        stale_after_seconds=metadata.stale_after_seconds,
                        recent_run_successes=[run.success for run in recent_runs],
                    ),
                )
            )
        return ConnectorCatalogResponse(connectors=entries, total=len(entries))

    async def get_history(
        self,
        source: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = DEFAULT_HISTORY_LIMIT,
        offset: int = 0,
    ) -> ConnectorHistoryResponse:
        """A page of one connector's stored history, oldest first.

        Raises `ConnectorSourceNotFoundError` (404) for a source with no
        registered connector — checked against the registry, not merely
        "does this table happen to have a row for it," so a genuinely
        unknown name is rejected the same way whether or not it happens to
        collide with real data.
        """
        load_builtin_connectors()
        if not default_connector_registry.has(source):
            raise ConnectorSourceNotFoundError(source, default_connector_registry.names())

        points = await self.external_data_repository.list_paginated(
            source, _GLOBAL_SYMBOL, start=start, end=end, limit=limit, offset=offset
        )
        total = await self.external_data_repository.count(
            source, _GLOBAL_SYMBOL, start=start, end=end
        )
        return ConnectorHistoryResponse(
            source=source,
            items=[
                ExternalDataPointDTO(timestamp=point.timestamp, value=point.value)
                for point in points
            ],
            pagination=ConnectorHistoryPagination(
                total=total,
                returned=len(points),
                has_more=offset + len(points) < total,
                limit=limit,
                offset=offset,
            ),
        )
