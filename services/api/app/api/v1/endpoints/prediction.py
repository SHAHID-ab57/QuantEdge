"""Live Prediction Service REST endpoints.

Turns a completed training job's saved model artifact into a usable live
output for the first time in this codebase — see `ARCHITECTURE.md` §
"Live Prediction Service". Every previous milestone (data, features,
datasets, experiments, training, evaluation) ends at a saved model artifact
and stops there; this is the first piece downstream of it: one prediction,
on demand, for one symbol.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.prediction import get_prediction_service
from app.schemas.prediction import (
    PredictionListResponse,
    PredictionResponse,
    PredictionRunRequest,
)
from app.services.prediction import PredictionService

router = APIRouter(tags=["prediction"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown training job, market, or prediction id",
        "content": {
            "application/json": {
                "examples": {
                    "training_job_not_found": {
                        "summary": "Unknown training job id",
                        "value": {
                            "code": "training_job_not_found",
                            "detail": "Training job 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found",
                        },
                    },
                    "market_not_found": {
                        "summary": "Unknown market symbol",
                        "value": {
                            "code": "market_not_found",
                            "detail": "Market 'ETHUSD' not found",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_409_CONFLICT: {
        "description": "The job has no trained model yet, or can't predict live",
        "content": {
            "application/json": {
                "examples": {
                    "prediction_not_available": {
                        "summary": "Job hasn't completed yet, or has no saved artifact",
                        "value": {
                            "code": "prediction_not_available",
                            "detail": (
                                "Training job 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 has no "
                                "trained model available for prediction (status is "
                                "'pending'; a job must be completed)"
                            ),
                        },
                    },
                    "live_feature_reconstruction_not_supported": {
                        "summary": "Job wasn't trained on real data (e.g. the placeholder adapter)",
                        "value": {
                            "code": "live_feature_reconstruction_not_supported",
                            "detail": (
                                "Training job 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 was not "
                                "trained on real data (no recorded feature_columns/"
                                "target_column), so a live feature vector cannot be "
                                "reconstructed for it"
                            ),
                        },
                    },
                }
            }
        },
    },
}

PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]
PredictionIdPath = Annotated[uuid.UUID, Path(description="Prediction id")]


@router.post(
    "/predictions/run",
    response_model=PredictionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run a fresh, live prediction for one market",
    description=(
        "Reconstructs a feature vector for the given symbol as of the latest available "
        "candle (or an explicit as_of), using the exact feature_set the training job's "
        "experiment recorded, runs the job's completed model, and persists the result. "
        "Runs synchronously — inference on a single row is fast."
    ),
    responses=_ERROR_RESPONSES,
)
async def run_prediction(
    body: PredictionRunRequest, service: PredictionServiceDep
) -> PredictionResponse:
    """Run and persist one live prediction."""
    return await service.run(body)


@router.get(
    "/predictions/{prediction_id}",
    response_model=PredictionResponse,
    summary="Get one past prediction",
    responses=_ERROR_RESPONSES,
)
async def get_prediction(
    prediction_id: PredictionIdPath, service: PredictionServiceDep
) -> PredictionResponse:
    """Return one persisted prediction by id."""
    return await service.get(prediction_id)


@router.get(
    "/predictions",
    response_model=PredictionListResponse,
    summary="List past predictions (Prediction History)",
    description=(
        "Every successful POST /predictions/run is recorded here, most recent first by "
        "default — filterable by training job, experiment, or symbol. Excludes backtest-"
        "generated predictions by default; pass backtest_run_id to see only one backtest "
        "run's own predictions (the Backtest Result view's drill-down)."
    ),
)
async def list_predictions(
    service: PredictionServiceDep,
    training_job_id: Annotated[
        uuid.UUID | None, Query(description="Only predictions from this training job")
    ] = None,
    experiment_id: Annotated[
        uuid.UUID | None, Query(description="Only predictions from this experiment")
    ] = None,
    symbol: Annotated[str | None, Query(description="Only predictions for this market")] = None,
    backtest_run_id: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Only this backtest run's own predictions, instead of the default "
                "(live predictions only, backtest ones excluded)"
            )
        ),
    ] = None,
    sort: Annotated[
        str, Query(description="Sort column; one of symbol, as_of, created_at")
    ] = "created_at",
    dir: Annotated[str, Query(description="Sort direction; asc or desc")] = "desc",
    limit: Annotated[
        int,
        Query(ge=1, le=get_settings().predictions_max_limit, description="Maximum rows per page"),
    ] = get_settings().predictions_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of rows to skip")] = 0,
) -> PredictionListResponse:
    """Return a page of past predictions matching the given filter/sort criteria."""
    return await service.search(
        training_job_id=training_job_id,
        experiment_id=experiment_id,
        symbol=symbol,
        backtest_run_id=backtest_run_id,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )
