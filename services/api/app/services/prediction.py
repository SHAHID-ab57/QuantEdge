"""Live Prediction Service — reconstructs a live feature vector for a completed
training job, runs its model, and persists the result.

Composes `TrainingJobService`/`ExperimentService`/`FeatureService` directly
(never a second copy of any of them), the same reuse
`app/services/evaluation.py`'s own module docstring already established for
this platform's other read-mostly services layered over an existing one:

- `TrainingJobService.get` resolves the job and its recorded
  `result_summary` (`feature_columns`, `target_column`, `artifact_uri`) —
  the authoritative record of exactly what a completed run actually trained
  on, never re-derived here.
- `FeatureService.build_raw` — "the one dataset-building path every
  consumer shares" (its own docstring already names "a live inference path"
  as a future consumer) — recomputes the same features the experiment's
  `feature_set` produced at training time, over fresh candles.
- `TrainingJobService.predict` runs the model and applies the identical
  normalization transform training used (`app/training/normalization.py`)
  — this module never touches a model adapter, a serialized artifact, or a
  `NormalizationStats` directly.

The only genuinely new work here is bounding *which* candles to fetch (the
one immediately at-or-before the requested `as_of`, plus enough history for
the largest feature's warmup) and shaping/persisting the result.
"""

import logging
import uuid

from app.features.dataset import FeatureRequest as DatasetFeatureRequest
from app.models.prediction import Prediction
from app.prediction.engine import PredictionEngine
from app.prediction.errors import (
    InvalidPredictionSortError,
    LiveFeatureReconstructionNotSupportedError,
    PredictionRunNotFoundError,
    TrainingFeatureSetMismatchError,
)
from app.prediction.registry import get_model_adapter_registry
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.predictions import SORT_COLUMNS as PREDICTION_SORT_COLUMNS
from app.repositories.predictions import PredictionFilters, PredictionRepository
from app.schemas.features import FeatureDatasetRequest, FeatureRequestItem
from app.schemas.prediction import (
    PredictionListResponse,
    PredictionResponse,
    PredictionRunRequest,
    PredictionSummaryDTO,
)
from app.services.candle_ingest import resolution_duration
from app.services.experiments import ExperimentService
from app.services.features import FeatureService
from app.services.market_query import CandleNotFoundError, MarketNotFoundError
from app.services.training import TrainingJobService
from app.training.errors import PredictionNotAvailableError, UndefinedFeatureValueError

logger = logging.getLogger("app.services.prediction")

#: Extra candles of headroom above a feature's own warmup requirement, so a
#: candle missing from the exact edge of the window (a real gap, or the
#: exchange not having posted the very latest candle yet) doesn't shrink
#: the reconstructed dataset to zero rows.
_WARMUP_BUFFER_CANDLES = 5


class PredictionService:
    """The one entry point routers use for every live prediction operation."""

    def __init__(
        self,
        repository: PredictionRepository,
        training_job_service: TrainingJobService,
        experiment_service: ExperimentService,
        feature_service: FeatureService,
        market_repository: MarketRepository,
        candle_repository: CandleRepository,
        engine: PredictionEngine,
    ) -> None:
        self.repository = repository
        self.training_job_service = training_job_service
        self.experiment_service = experiment_service
        self.feature_service = feature_service
        self.market_repository = market_repository
        self.candle_repository = candle_repository
        self.engine = engine

    async def run(self, request: PredictionRunRequest) -> PredictionResponse:
        """Reconstruct a live feature vector, predict, and persist the result.

        Runs synchronously — inference on a single reconstructed row is fast;
        the (already-known) need for a worker/queue applies to *training*
        (`TrainingJobService.run`'s own docstring), not to this.
        """
        job = await self.training_job_service.get(request.training_job_id)
        summary = job.result_summary or {}
        artifact_uri = summary.get("artifact_uri")
        if job.status != "completed" or not artifact_uri:
            raise PredictionNotAvailableError(request.training_job_id, job.status)

        feature_columns: list[str] | None = summary.get("feature_columns")
        target_column: str | None = summary.get("target_column")
        if not feature_columns or not target_column or not job.timeframe:
            raise LiveFeatureReconstructionNotSupportedError(request.training_job_id)

        experiment = await self.experiment_service.get(uuid.UUID(job.experiment_id))
        if not experiment.feature_set:
            raise LiveFeatureReconstructionNotSupportedError(request.training_job_id)

        market = await self.market_repository.get_by_symbol(request.symbol)
        if market is None:
            raise MarketNotFoundError(request.symbol)

        timeframe = job.timeframe
        interval = resolution_duration(timeframe)
        if request.as_of is not None:
            reference_time = request.as_of
        else:
            latest = await self.candle_repository.get_latest_candle(market.id, timeframe)
            if latest is None:
                raise CandleNotFoundError(request.symbol, timeframe)
            reference_time = latest.open_time

        dataset_feature_requests = [
            DatasetFeatureRequest(feature=item.feature, params=dict(item.params))
            for item in experiment.feature_set
        ]
        # `FeatureService.build_raw` itself widens the *candle* fetch by
        # `warmup` on top of whatever `limit` we pass (its own docstring: "a
        # researcher who asks for 500 rows with an SMA(50) gets 500 rows —
        # not 450"), so `limit` here is the number of *output rows* wanted
        # post-warmup-trim, not the candle count — `rows_wanted` rows,
        # ending at `reference_time`, needs `warmup + rows_wanted` real
        # candles in range, which `start` below provides exactly.
        warmup = self.feature_service.builder.required_warmup(dataset_feature_requests)
        rows_wanted = _WARMUP_BUFFER_CANDLES + 1
        candles_needed = warmup + rows_wanted

        dataset, _database_time_ms = await self.feature_service.build_raw(
            request.symbol,
            FeatureDatasetRequest(
                timeframe=timeframe,
                start=reference_time - interval * (candles_needed - 1),
                # Half-open `[start, end)` — one full interval past the
                # reference time so a candle exactly *at* it is included.
                end=reference_time + interval,
                limit=rows_wanted,
                features=[
                    FeatureRequestItem(feature=item.feature, params=item.params)
                    for item in experiment.feature_set
                ],
                drop_warmup=True,
            ),
        )
        # `FeatureDatasetBuilder.build` already raises `EmptyDatasetError` if
        # every row was dropped as warmup — `dataset.row_count` is always
        # >= 1 by the time control reaches here.
        last_row = dataset.rows[-1]
        as_of = dataset.timestamps[-1]
        column_index = {column.name: index for index, column in enumerate(dataset.columns)}

        row: list[float] = []
        for name in feature_columns:
            index = column_index.get(name)
            if index is None:
                raise TrainingFeatureSetMismatchError(request.training_job_id, name)
            value = last_row[index]
            if value is None or isinstance(value, str):
                raise UndefinedFeatureValueError(name)
            row.append(float(value))

        predict_response = await self.training_job_service.predict(request.training_job_id, [row])
        outcome = self.engine.assemble(
            target_column=target_column,
            target_config=experiment.target_config,
            as_of=as_of,
            predict_response=predict_response,
        )

        adapter_registry = get_model_adapter_registry()
        model_kind = (
            adapter_registry.get(job.model_type).metadata.model_kind
            if adapter_registry.has(job.model_type)
            else "unknown"
        )

        prediction = Prediction(
            training_job_id=request.training_job_id,
            experiment_id=uuid.UUID(job.experiment_id),
            symbol=request.symbol,
            timeframe=timeframe,
            target_column=outcome.target_column,
            horizon=outcome.horizon,
            as_of=outcome.as_of,
            predicted_value=outcome.predicted_value,
            confidence=outcome.confidence,
            probabilities=outcome.probabilities,
            classes=outcome.classes,
            feature_columns=list(feature_columns),
            model_type=job.model_type,
            model_kind=model_kind,
            actual_outcome=None,
        )
        created = await self.repository.create(prediction)
        logger.info(
            "Predicted %s=%s for %s/%s as of %s (job=%s)",
            outcome.target_column,
            outcome.predicted_value,
            request.symbol,
            timeframe,
            as_of.isoformat(),
            request.training_job_id,
        )
        return PredictionResponse.from_model(created)

    async def get(self, prediction_id: uuid.UUID) -> PredictionResponse:
        prediction = await self.repository.get_by_id(prediction_id)
        if prediction is None:
            raise PredictionRunNotFoundError(prediction_id)
        return PredictionResponse.from_model(prediction)

    async def search(
        self,
        *,
        training_job_id: uuid.UUID | None,
        experiment_id: uuid.UUID | None,
        symbol: str | None,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> PredictionListResponse:
        """Prediction History's list view — every past run, paginated."""
        if sort not in PREDICTION_SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidPredictionSortError(sort, direction, tuple(PREDICTION_SORT_COLUMNS))

        filters = PredictionFilters(
            training_job_id=training_job_id, experiment_id=experiment_id, symbol=symbol
        )
        predictions, total = await self.repository.search(
            filters, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return PredictionListResponse(
            predictions=[PredictionSummaryDTO.from_model(p) for p in predictions],
            total=total,
            limit=limit,
            offset=offset,
        )
