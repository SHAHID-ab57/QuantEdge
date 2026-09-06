"""External data ingestion — fetch via a registered connector, validate,
persist idempotently. Mirrors `app.services.candle_ingest`'s own split
exactly: a connector only fetches and shapes data (never touches the
database); this module is the one place a fetch result is turned into
stored rows, for any connector, not one ingestion function per source.

Idempotent: re-running the same range never duplicates rows. Unlike
candle ingestion, the backstop here is **not** solely the database's own
unique constraint — `ExternalDataPoint`'s own docstring explains why a
`NULL` `symbol` (Fear & Greed's own case) can't rely on that alone — so
this module checks existing timestamps itself, in the application layer,
*before* ever inserting, which is correct regardless of backend.

One connector-specific exception: a source whose `ConnectorMetadata
.revisable` is `True` (DefiLlama's TVL, whose upstream provider still
settles an in-progress day's own figure after it first appears — see
`app.connectors.defillama`) additionally *overwrites* an already-stored
point when a re-fetch reports a genuinely different value, rather than
skipping it as a duplicate. Every connector before DefiLlama defaults to
`revisable=False` and is completely unaffected — `_persist_points` never
even loads existing values to compare unless a connector opts in.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.connectors import load_builtin_connectors
from app.connectors.base import RawDataPoint
from app.connectors.registry import default_registry as default_connector_registry
from app.core.config import get_settings
from app.db.engine import get_engine
from app.models.external_data import ExternalDataPoint
from app.repositories.external_data import ExternalDataRepository

logger = logging.getLogger("app.services.external_data_ingest")


class ExternalDataIngestError(RuntimeError):
    """Raised when external data ingestion cannot proceed safely."""


@dataclass(frozen=True)
class ExternalDataIngestReport:
    """Outcome of one ingestion run for one source."""

    source: str
    start: datetime
    end: datetime
    received: int
    inserted: int
    #: Count of already-stored points overwritten because a re-fetch
    #: reported a genuinely different value — always `0` for a connector
    #: whose `ConnectorMetadata.revisable` is `False` (every connector
    #: before DefiLlama); see `_persist_points`.
    updated: int
    duplicates_skipped: int
    rejected: int
    duration_seconds: float


async def ingest_external_data(
    *,
    source: str,
    start: datetime,
    end: datetime,
    session: AsyncSession | None = None,
) -> ExternalDataIngestReport:
    """Fetch, validate, and persist external data points for one source.

    Args:
        source: A registered connector's own source name (e.g. `"fear_greed"`).
        start: Range start (inclusive, timezone-aware UTC) — see
            `Connector.fetch`'s own docstring for why this table's range is
            inclusive on both ends, unlike `Candle`'s half-open convention.
        end: Range end (inclusive, timezone-aware UTC).
        session: Database session; built from the configured engine when
            omitted. Pass a session with no active transaction.

    Returns:
        A report with received/inserted/duplicates_skipped/rejected counts
        and elapsed time.

    Raises:
        ExternalDataIngestError: When the range or source is invalid, or
            the database is not configured.
    """
    started_at = perf_counter()
    if start.tzinfo is None or end.tzinfo is None:
        raise ExternalDataIngestError("start and end must be timezone-aware datetimes")
    if end < start:
        raise ExternalDataIngestError("end must not be before start")

    load_builtin_connectors()
    if not default_connector_registry.has(source):
        raise ExternalDataIngestError(
            f"Unknown connector source {source!r}; registered: "
            f"{', '.join(default_connector_registry.names())}"
        )

    logger.info(
        "External data ingestion started (source=%s range=[%s, %s])",
        source,
        start.isoformat(),
        end.isoformat(),
    )

    owns_session = session is None
    if session is None:
        engine = get_engine()
        if engine is None:
            raise ExternalDataIngestError("Database is not configured")
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()

    connector = default_connector_registry.get(source)
    try:
        points = await connector.fetch(start, end)
        inserted, updated, duplicates_skipped, rejected = await _persist_points(
            session, source, points, revisable=connector.metadata.revisable
        )
    finally:
        aclose = getattr(connector, "aclose", None)
        if aclose is not None:
            await aclose()
        if owns_session:
            await session.close()

    return ExternalDataIngestReport(
        source=source,
        start=start,
        end=end,
        received=len(points),
        inserted=inserted,
        updated=updated,
        duplicates_skipped=duplicates_skipped,
        rejected=rejected,
        duration_seconds=perf_counter() - started_at,
    )


async def _persist_points(
    session: AsyncSession, source: str, points: Sequence[RawDataPoint], *, revisable: bool = False
) -> tuple[int, int, int, int]:
    """Insert points idempotently; return (inserted, updated, duplicates_skipped, rejected).

    Mirrors `app.services.candle_ingest._persist_candles` exactly: records
    whose `(symbol, timestamp)` already exist are skipped without touching
    the database; a row that still fails at the database level (a race,
    or a genuine constraint violation) is isolated via a savepoint,
    logged, and counted as rejected — never silently accepted.

    `revisable=False` (every connector before DefiLlama) is byte-for-byte
    the original behavior: existing timestamps are loaded once and any
    collision is an unconditional skip, no value ever compared or
    overwritten. `revisable=True` additionally loads each existing point's
    own stored `value` and, on a timestamp collision, overwrites it via
    `ExternalDataRepository.update_value` *only* when the freshly-fetched
    value genuinely differs — an unchanged re-fetch is still just a
    duplicate skip, not a wasted write. See `ConnectorMetadata.revisable`'s
    own docstring for why this exists at all (DefiLlama's TVL, confirmed
    to still be settling for an in-progress day) and
    `app.connectors.defillama` for the full investigation.
    """
    repository = ExternalDataRepository(session)
    # `symbol` genuinely varies per point for a future per-market connector
    # (Fear & Greed's own points are always `None`) — existing keys are
    # loaded per distinct symbol actually present, not assumed to be one
    # value for the whole batch.
    existing_by_symbol: dict[str | None, set[datetime]] = {}
    existing_values_by_symbol: dict[str | None, dict[datetime, float]] = {}

    pending: list[ExternalDataPoint] = []
    to_update: list[tuple[str | None, datetime, float, dict[str, Any] | None]] = []
    duplicates_skipped = 0
    for point in points:
        if point.symbol not in existing_by_symbol:
            if revisable:
                existing_values = await repository.list_existing_values(source, point.symbol)
                existing_values_by_symbol[point.symbol] = existing_values
                existing_by_symbol[point.symbol] = set(existing_values)
            else:
                existing_by_symbol[point.symbol] = await repository.list_existing_timestamps(
                    source, point.symbol
                )
        existing = existing_by_symbol[point.symbol]
        if point.timestamp in existing:
            if (
                revisable
                and existing_values_by_symbol[point.symbol][point.timestamp] != point.value
            ):
                to_update.append((point.symbol, point.timestamp, point.value, point.raw_payload))
            else:
                duplicates_skipped += 1
            continue
        existing.add(point.timestamp)
        pending.append(
            ExternalDataPoint(
                source=source,
                symbol=point.symbol,
                timestamp=point.timestamp,
                value=point.value,
                raw_payload=point.raw_payload,
            )
        )

    if not pending and not to_update:
        return 0, 0, duplicates_skipped, 0

    # No explicit `session.begin()` here, deliberately: the existing-keys
    # reads above already autobegan a transaction on this session (plain
    # AsyncSession autobegin), so wrapping this block in a second explicit
    # `begin()` would raise `InvalidRequestError: A transaction is already
    # begun on this Session.` `begin_nested()` (a SAVEPOINT) only needs an
    # already-open outer transaction, which autobegin already provided —
    # this is what `_persist_candles` gets for free by opening its own
    # `session.begin()` *before* loading existing keys; this module reads
    # existing keys per-symbol as it goes, so the ordering is reversed and
    # an explicit outer `begin()` here would double-begin instead.
    updated = 0
    for symbol, timestamp, value, raw_payload in to_update:
        await repository.update_value(
            source, symbol, timestamp, value=value, raw_payload=raw_payload
        )
        updated += 1

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
                "Rejecting external data point (source=%s symbol=%s timestamp=%s): "
                "rejected by the database (%s)",
                source,
                row.symbol,
                row.timestamp.isoformat(),
                exc.orig,
            )
    await session.commit()

    return inserted, updated, duplicates_skipped, rejected


async def run_ingest_once(
    *, source: str, start: datetime | None = None, end: datetime | None = None
) -> ExternalDataIngestReport:
    """Run one ingestion pass synchronously (CLI and manual verification).

    Defaults `end` to now and `start` to a generous, connector-agnostic
    lookback (`external_data_sync_backfill_days`) when omitted — the same
    "seed a full history when nothing is stored yet" role
    `CandleSyncScheduler`'s own `backfill_days` plays for candles.
    """
    settings = get_settings()
    resolved_end = end if end is not None else datetime.now(UTC)
    resolved_start = (
        start
        if start is not None
        else resolved_end - timedelta(days=settings.external_data_sync_backfill_days)
    )
    report = await ingest_external_data(source=source, start=resolved_start, end=resolved_end)
    logger.info(
        "External data ingestion completed (source=%s): received=%d inserted=%d updated=%d "
        "duplicates_skipped=%d rejected=%d in %.2fs",
        report.source,
        report.received,
        report.inserted,
        report.updated,
        report.duplicates_skipped,
        report.rejected,
        report.duration_seconds,
    )
    return report
