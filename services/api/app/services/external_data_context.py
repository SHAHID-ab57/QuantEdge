"""Bridges `FeatureContext.external_data` to the database — the one place
a connector-backed feature's declared `external_sources` are resolved
into pre-fetched rows, shared by both dataset-building services
(`app.services.features.FeatureService` and
`app.services.ml_datasets.MLDatasetService`) so a feature like
`fear_greed` computes identically wherever a dataset is built from —
the same no-train/serve-skew guarantee `app.features.base`'s own module
docstring states as this whole context's reason to exist. Without this
shared helper, wiring the two services independently would risk the
exact silent, "sometimes null for no visible reason" drift that
guarantee exists to prevent.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.features.base import ExternalDataPoint, OHLCVPoint
from app.features.dataset import FeatureRequest
from app.features.errors import FeatureNotFoundError
from app.features.pipeline import FeaturePipeline
from app.repositories.external_data import ExternalDataRepository

#: How far before the earliest requested candle to look for an external
#: data point — generous enough for a source with occasional gaps in its
#: own update cadence (a connector down for a few days, a holiday with no
#: publish) while still bounding the query; the most recent point at or
#: before the earliest candle is all `most_recent_value_at_or_before`
#: ever needs, however far back it actually sits within this window.
EXTERNAL_DATA_LOOKBACK_DAYS = 30


async def resolve_external_data(
    *,
    pipeline: FeaturePipeline,
    requests: Sequence[FeatureRequest],
    candles: Sequence[OHLCVPoint],
    repository: ExternalDataRepository,
) -> dict[str, list[ExternalDataPoint]]:
    """Pre-fetch every connector source any requested feature declares.

    Resolves the *union* of `FeatureMetadata.external_sources` across
    every requested feature, then loads each distinct source exactly
    once — one query per source, never one per candle or one per
    request — for the whole `[earliest candle - lookback, latest candle]`
    window in a single pass.

    An unresolvable request (unknown feature name) is silently skipped
    here — `FeatureDatasetBuilder.build` itself is what reports that as a
    `FeatureFailure`; this helper's only job is finding out what a
    *resolvable* request needs.

    Global-only today (queries `symbol=None`): every registered connector
    so far (`fear_greed`) reports one source-wide value, never a
    per-market one. A future per-symbol connector would need this
    extended to also resolve `symbol`-scoped rows.
    """
    if not candles:
        return {}

    sources: set[str] = set()
    for request in requests:
        try:
            metadata = pipeline.describe(request.feature)
        except FeatureNotFoundError:
            continue
        sources.update(metadata.external_sources)
    if not sources:
        return {}

    start = candles[0].open_time - timedelta(days=EXTERNAL_DATA_LOOKBACK_DAYS)
    end = candles[-1].open_time

    external_data: dict[str, list[ExternalDataPoint]] = {}
    for source in sorted(sources):
        rows = await repository.list_between(source, None, start=start, end=end)
        external_data[source] = [
            ExternalDataPoint(timestamp=_as_utc(row.timestamp), value=row.value) for row in rows
        ]
    return external_data


def _as_utc(value: datetime) -> datetime:
    """Normalize to a timezone-aware UTC datetime.

    SQLite (this platform's in-memory test database) round-trips a
    ``DateTime(timezone=True)`` column as a *naive* datetime — the same
    quirk `app.services.candle_sync._catch_up_window` already works
    around for `Candle.open_time`. Comparing that naive value against
    the timezone-aware candle timestamps `most_recent_value_at_or_before`
    receives would otherwise raise `TypeError` on SQLite specifically,
    while working by accident on Postgres (which does preserve the
    offset) — this makes the two backends agree.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
