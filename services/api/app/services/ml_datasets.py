"""ML dataset service — the bridge between stored candles and the ML Dataset Builder.

Mirrors `app.services.features.FeatureService` deliberately: the same
candle-loading join (`load_candle_points`, shared with the indicator and
feature services), the same warmup-widen-then-cap-rows dance, now widened
by feature-warmup *plus* target-horizon so a requested row count survives
both trims, not just one.
"""

import logging
from dataclasses import dataclass, replace

from app.features.ai_extensions import SplitRatios
from app.features.dataset import FeatureRequest
from app.ml_datasets.dataset import MLDataset, MLDatasetBuilder, TargetRequest
from app.ml_datasets.export import EXPORT_FORMATS, dataset_filename
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.schemas.features import FeatureRequestItem
from app.schemas.ml_datasets import (
    MLDatasetRequest,
    MLDatasetResponse,
    MLTargetRequestItem,
    TargetCatalogResponse,
    TargetDTO,
)
from app.services.candle_points import load_candle_points
from app.services.market_query import validate_limit

logger = logging.getLogger("app.services.ml_datasets")


@dataclass(frozen=True, slots=True)
class ExportedMLDataset:
    """A serialized ML dataset ready to be streamed as a file download."""

    content: str | bytes
    media_type: str
    filename: str


@dataclass(frozen=True)
class MLDatasetService:
    """Business logic for the ML Dataset Builder REST API."""

    candle_repository: CandleRepository
    market_repository: MarketRepository
    builder: MLDatasetBuilder
    default_limit: int
    max_limit: int

    def list_targets(self) -> TargetCatalogResponse:
        """Return the full target catalogue.

        Reads straight from the registry, so a target added to
        `app/ml_datasets/targets/` appears here with no change to this
        service — the same extensibility guarantee `FeatureService.list_features`
        already gives feature generators.
        """
        load_builtin_targets()
        metadata = self.builder.target_pipeline.describe_all()
        targets = [TargetDTO.from_metadata(entry) for entry in metadata]
        categories = sorted({entry.category for entry in metadata})
        return TargetCatalogResponse(targets=targets, total=len(targets), categories=categories)

    def get_target(self, name: str) -> TargetDTO:
        """Return one target generator's metadata, or raise `TargetNotFoundError`."""
        load_builtin_targets()
        return TargetDTO.from_metadata(self.builder.target_pipeline.describe(name))

    async def build_dataset(self, symbol: str, request: MLDatasetRequest) -> MLDatasetResponse:
        """Build, validate, and split an ML dataset for one market/timeframe/range."""
        ml_dataset, database_time_ms = await self._build(symbol, request)
        return MLDatasetResponse.from_ml_dataset(
            ml_dataset,
            database_time_ms=database_time_ms,
            preview_rows=request.preview_rows,
        )

    async def export_dataset(
        self, symbol: str, request: MLDatasetRequest, fmt: str
    ) -> ExportedMLDataset:
        """Build the same ML dataset and serialize it whole, for a file download.

        Deliberately ignores `preview_rows`, matching
        `FeatureService.export_dataset`'s exact reasoning: an export
        truncated to what a preview happened to show would silently
        produce a partial training set.
        """
        ml_dataset, _ = await self._build(symbol, request)
        export_format = EXPORT_FORMATS[fmt]
        return ExportedMLDataset(
            content=export_format.serialize(ml_dataset),
            media_type=export_format.media_type,
            filename=dataset_filename(ml_dataset, export_format.extension),
        )

    async def _build(self, symbol: str, request: MLDatasetRequest) -> tuple[MLDataset, float]:
        load_builtin_targets()
        feature_requests = _to_feature_requests(request.features)
        target_requests = _to_target_requests(request.targets)
        ratios = SplitRatios(
            train=request.split_train,
            validation=request.split_validation,
            test=request.split_test,
        )

        warmup = self.builder.feature_builder.required_warmup(feature_requests)
        horizon = self.builder.required_horizon(target_requests)
        widen = warmup + horizon

        resolved_limit = self.default_limit if request.limit is None else request.limit
        # Validate what the *caller* asked for, before widening — the same
        # "reject, don't silently clamp" discipline `FeatureService._build`
        # already uses.
        validate_limit(resolved_limit, self.max_limit)

        needs_widening = request.drop_warmup or request.drop_undefined_targets
        widened = min(resolved_limit + widen, self.max_limit) if needs_widening else None

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

        ml_dataset = self.builder.build(
            symbol,
            request.timeframe,
            loaded.points,
            feature_requests,
            target_requests,
            drop_warmup=request.drop_warmup,
            drop_undefined_targets=request.drop_undefined_targets,
            split_ratios=ratios,
        )
        ml_dataset = _cap_rows(ml_dataset, resolved_limit)
        logger.info(
            "Built ML dataset (symbol=%s timeframe=%s features=%d targets=%d rows=%d db=%.1fms)",
            symbol,
            request.timeframe,
            len(feature_requests),
            len(target_requests),
            ml_dataset.dataset.row_count,
            loaded.database_time_ms,
        )
        return ml_dataset, loaded.database_time_ms


def _to_feature_requests(items: list[FeatureRequestItem]) -> list[FeatureRequest]:
    """Map wire request items onto the feature builder's own request type."""
    return [FeatureRequest(feature=item.feature, params=dict(item.params)) for item in items]


def _to_target_requests(items: list[MLTargetRequestItem]) -> list[TargetRequest]:
    """Map wire request items onto the ML dataset builder's own request type."""
    return [TargetRequest(target=item.target, params=dict(item.params)) for item in items]


def _cap_rows(ml_dataset: MLDataset, limit: int) -> MLDataset:
    """Trim the assembled dataset (and re-split it) to at most `limit` rows, keeping the earliest.

    Mirrors `app.services.features._cap_rows`: the candle query already
    loaded the first `limit + warmup + horizon` candles of the range in
    ascending order, so dropping from the end returns exactly the window
    the caller's range and limit describe. The split is recomputed over the
    capped matrix rather than merely truncated, so the train/validation/
    test ratios still describe *this* response's rows, not the wider
    pre-cap set.
    """
    if ml_dataset.dataset.row_count <= limit:
        return ml_dataset
    dataset = ml_dataset.dataset
    capped = replace(
        dataset,
        timestamps=dataset.timestamps[:limit],
        rows=dataset.rows[:limit],
        quality=replace(dataset.quality, rows_returned=limit),
    )
    split = ChronologicalSplitter().split(capped, ml_dataset.split_ratios)
    return replace(ml_dataset, dataset=capped, split=split)
