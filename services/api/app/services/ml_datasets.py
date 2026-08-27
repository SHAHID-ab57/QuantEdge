"""ML dataset service — the bridge between stored candles and the ML Dataset Builder.

Mirrors `app.services.features.FeatureService` deliberately: the same
candle-loading join (`load_candle_points`, shared with the indicator and
feature services), the same warmup-widen-then-cap-rows dance, now widened
by feature-warmup *plus* target-horizon so a requested row count survives
both trims, not just one.
"""

import logging
import uuid
from dataclasses import dataclass, replace

from app.features.ai_extensions import SplitRatios
from app.features.dataset import FeatureRequest
from app.ml_datasets.dataset import MLDataset, MLDatasetBuilder, TargetRequest
from app.ml_datasets.errors import InvalidMLDatasetBuildSortError, MLDatasetBuildNotFoundError
from app.ml_datasets.export import EXPORT_FORMATS, dataset_filename
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from app.models.ml_dataset_build import MLDatasetBuild
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.ml_dataset_builds import (
    SORT_COLUMNS,
    MLDatasetBuildFilters,
    MLDatasetBuildRepository,
)
from app.schemas.features import FeatureRequestItem
from app.schemas.ml_datasets import (
    MLDatasetBuildDetailResponse,
    MLDatasetBuildListResponse,
    MLDatasetBuildSummaryDTO,
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
    #: Persists every `build_dataset` call into Dataset History — see
    #: `app/models/ml_dataset_build.py`. Deliberately not used by
    #: `build_ml_dataset`/`export_dataset` (see their own docstrings): only an
    #: explicit "Build ML Dataset" click from `/ml-datasets` should grow this
    #: history, never a Training Framework job's internal reuse of this same
    #: service, and never a re-export of an already-recorded build.
    build_repository: MLDatasetBuildRepository
    history_default_limit: int = 20
    history_max_limit: int = 100

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
        """Build, validate, and split an ML dataset for one market/timeframe/range.

        Also persists the *full, untruncated* build to Dataset History
        (`app/models/ml_dataset_build.py`) — independent of `preview_rows`,
        which only affects what this call itself returns — so a later visit
        to Dataset History can reopen the exact same dataset, rows included,
        never merely what happened to fit in that request's own preview cap.
        """
        ml_dataset, database_time_ms = await self._build(symbol, request)
        full = MLDatasetResponse.from_ml_dataset(
            ml_dataset, database_time_ms=database_time_ms, preview_rows=None
        )
        await self._record_build(symbol, ml_dataset, full)
        if request.preview_rows is None:
            return full
        return MLDatasetResponse.from_ml_dataset(
            ml_dataset,
            database_time_ms=database_time_ms,
            preview_rows=request.preview_rows,
        )

    async def build_ml_dataset(self, symbol: str, request: MLDatasetRequest) -> MLDataset:
        """Build, validate, and split an ML dataset, returning the engine object itself.

        The one seam the Machine Learning Training Framework uses to get
        real training data (`app/training/dataset_loader.py`) — it needs
        the raw `MLDataset` (its `split.train`/`validation`/`test` row
        matrices), not a wire `MLDatasetResponse`. Calls the exact same
        `_build` every REST endpoint on this service already goes through;
        this is not a second dataset-building path.
        """
        ml_dataset, _ = await self._build(symbol, request)
        return ml_dataset

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

    async def list_builds(
        self,
        *,
        symbol: str | None,
        timeframe: str | None,
        quality_passed: bool | None,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> MLDatasetBuildListResponse:
        """Dataset History's list view — every past build this session recorded, paginated."""
        if sort not in SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidMLDatasetBuildSortError(sort, direction, tuple(SORT_COLUMNS))

        filters = MLDatasetBuildFilters(
            symbol=symbol, timeframe=timeframe, quality_passed=quality_passed
        )
        builds, total = await self.build_repository.search(
            filters, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return MLDatasetBuildListResponse(
            builds=[MLDatasetBuildSummaryDTO.from_model(build) for build in builds],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_build(self, build_id: uuid.UUID) -> MLDatasetBuildDetailResponse:
        """One past build's full record, rows included — Dataset History's detail view."""
        build = await self.build_repository.get_by_id(build_id)
        if build is None:
            raise MLDatasetBuildNotFoundError(build_id)
        return MLDatasetBuildDetailResponse.from_model(build)

    async def delete_build(self, build_id: uuid.UUID) -> None:
        """Remove one past build from Dataset History — the underlying candles are untouched."""
        build = await self.build_repository.get_by_id(build_id)
        if build is None:
            raise MLDatasetBuildNotFoundError(build_id)
        await self.build_repository.delete(build)

    async def _record_build(
        self, symbol: str, ml_dataset: MLDataset, full: MLDatasetResponse
    ) -> None:
        """Persist one `build_dataset` call to Dataset History.

        Best-effort: a failure here must never fail the build itself (the
        researcher already has their dataset on screen) — logged and
        swallowed, matching `TrainingJobService._mark_experiment_failed`'s
        own "don't let bookkeeping sink the primary outcome" precedent.
        """
        try:
            await self.build_repository.create(
                MLDatasetBuild(
                    ml_dataset_id=ml_dataset.ml_dataset_id,
                    symbol=symbol,
                    timeframe=full.timeframe,
                    row_count=full.meta.total_rows,
                    column_count=len(full.columns),
                    feature_count=len(full.feature_columns),
                    target_count=len(full.target_columns),
                    quality_passed=full.validation.passed,
                    payload=full.model_dump(mode="json"),
                )
            )
        except Exception:  # noqa: BLE001 - best-effort; the build itself already succeeded
            logger.exception(
                "Failed to record ML dataset build %s to Dataset History", ml_dataset.ml_dataset_id
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
