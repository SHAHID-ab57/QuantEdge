"""Feature service — the bridge between stored candles and the feature engine.

The only place the two halves meet: the engine knows nothing about markets,
timeframes, or the database, and the repositories know nothing about
features. Keeping the join here is what lets the same generators be driven
later by a training job, a backtest runner, or a live inference path that
has candles from somewhere else entirely.

Routers never touch SQL, and the engine never touches the ORM — both
platform conventions hold, and candle loading itself is shared with the
indicator service via ``load_candle_points`` rather than reimplemented.
"""

import logging
from dataclasses import dataclass, replace

from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDataset, FeatureDatasetBuilder, FeatureRequest
from app.features.export import EXPORT_FORMATS, dataset_filename
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.features import (
    FeatureCatalogResponse,
    FeatureDatasetRequest,
    FeatureDatasetResponse,
    FeatureDTO,
    FeatureRequestItem,
)
from app.services.candle_points import load_candle_points
from app.services.market_query import validate_limit

logger = logging.getLogger("app.services.features")


@dataclass(frozen=True, slots=True)
class ExportedDataset:
    """A serialized dataset ready to be streamed as a file download.

    ``content`` is ``str | bytes`` — every format registered today
    (``EXPORT_FORMATS``) is text, but a future binary format (Parquet)
    would return ``bytes`` here with no change to this type or to the
    endpoint that streams it.
    """

    content: str | bytes
    media_type: str
    filename: str


@dataclass(frozen=True)
class FeatureService:
    """Business logic for the feature engineering REST API."""

    candle_repository: CandleRepository
    market_repository: MarketRepository
    builder: FeatureDatasetBuilder
    default_limit: int
    max_limit: int

    def list_features(self) -> FeatureCatalogResponse:
        """Return the full feature catalogue.

        Reads straight from the registry, so a generator added to
        ``app/features/builtin/`` appears here with no change to this
        service — and so does a feature backed by a newly-registered
        indicator.
        """
        load_builtin_features()
        metadata = self.builder.pipeline.describe_all()
        features = [FeatureDTO.from_metadata(entry) for entry in metadata]
        categories = sorted({entry.category for entry in metadata})
        return FeatureCatalogResponse(
            features=features,
            total=len(features),
            categories=categories,
        )

    def get_feature(self, name: str) -> FeatureDTO:
        """Return one generator's metadata, or raise ``FeatureNotFoundError``."""
        load_builtin_features()
        return FeatureDTO.from_metadata(self.builder.pipeline.describe(name))

    async def build_dataset(
        self, symbol: str, request: FeatureDatasetRequest
    ) -> FeatureDatasetResponse:
        """Build a feature dataset for one market/timeframe/range."""
        dataset, database_time_ms = await self._build(symbol, request)
        return FeatureDatasetResponse.from_dataset(
            dataset,
            database_time_ms=database_time_ms,
            preview_rows=request.preview_rows,
        )

    async def export_dataset(
        self, symbol: str, request: FeatureDatasetRequest, fmt: str
    ) -> ExportedDataset:
        """Build a dataset and serialize it whole, for a file download.

        Deliberately ignores ``preview_rows``: an export is the complete
        dataset by definition. Exporting only what a preview showed is the
        single most damaging thing this endpoint could do — a researcher
        would train on a truncated matrix with nothing to indicate it.

        Looks the format up in ``EXPORT_FORMATS`` rather than branching on
        it, so a future binary format (Parquet) needs no change here — see
        ``app/features/export.py``.
        """
        dataset, _ = await self._build(symbol, request)
        export_format = EXPORT_FORMATS[fmt]
        return ExportedDataset(
            content=export_format.serialize(dataset),
            media_type=export_format.media_type,
            filename=dataset_filename(dataset, export_format.extension),
        )

    async def _build(
        self, symbol: str, request: FeatureDatasetRequest
    ) -> tuple[FeatureDataset, float]:
        """Load candles once, then run every requested generator over them.

        The candle window is widened by the largest warmup across the
        requested features before loading, so a researcher who asks for 500
        rows with an SMA(50) gets 500 rows — not 450. Without this, adding
        a longer-period feature would silently shrink an existing dataset,
        which is exactly the kind of quiet, hard-to-notice change that
        makes results irreproducible.
        """
        load_builtin_features()
        requests = _to_requests(request.features)
        warmup = self.builder.required_warmup(requests)

        resolved_limit = self.default_limit if request.limit is None else request.limit
        # Validate what the *caller* asked for, before widening. Widening
        # first would clamp an over-limit request to the maximum and
        # silently accept it, which is worse than rejecting it: the caller
        # would get far less data than they requested with no indication.
        validate_limit(resolved_limit, self.max_limit)

        widened = min(resolved_limit + warmup, self.max_limit) if request.drop_warmup else None

        loaded = await load_candle_points(
            symbol=symbol,
            timeframe=request.timeframe,
            market_repository=self.market_repository,
            candle_repository=self.candle_repository,
            default_limit=self.default_limit,
            max_limit=self.max_limit,
            start=request.start,
            end=request.end,
            limit=widened if widened is not None else request.limit,
        )

        dataset = self.builder.build(
            symbol,
            request.timeframe,
            loaded.points,
            requests,
            drop_warmup=request.drop_warmup,
        )
        # `limit` means "rows in the dataset", not "candles loaded": the
        # extra candles above were read solely to satisfy warmup, and
        # returning them would make the row count depend on which features
        # happened to be requested.
        dataset = _cap_rows(dataset, resolved_limit)
        logger.info(
            "Built dataset (symbol=%s timeframe=%s features=%d rows=%d db=%.1fms)",
            symbol,
            request.timeframe,
            len(requests),
            dataset.row_count,
            loaded.database_time_ms,
        )
        return dataset, loaded.database_time_ms


def _to_requests(items: list[FeatureRequestItem]) -> list[FeatureRequest]:
    """Map wire request items onto the builder's own request type."""
    return [FeatureRequest(feature=item.feature, params=dict(item.params)) for item in items]


def _cap_rows(dataset: FeatureDataset, limit: int) -> FeatureDataset:
    """Trim a dataset to at most ``limit`` rows, keeping the earliest.

    Keeps the *earliest* surviving rows because the candle query already
    took the first ``limit + warmup`` candles of the range in ascending
    order: dropping from the end therefore returns exactly the window the
    caller's range and limit describe, with the warmup consumed off the
    front where it belongs.
    """
    if dataset.row_count <= limit:
        return dataset
    return replace(
        dataset,
        timestamps=dataset.timestamps[:limit],
        rows=dataset.rows[:limit],
        # `rows_returned` must describe what the caller actually gets back,
        # not the pre-cap row count the quality report was computed against.
        quality=replace(dataset.quality, rows_returned=limit),
    )
