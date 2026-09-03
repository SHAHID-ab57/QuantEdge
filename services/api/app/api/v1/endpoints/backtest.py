"""Backtesting Engine REST endpoints.

Walks a trained model over a historical date range, one live prediction and
grade per step (both reused completely unmodified — see
`app/services/backtest.py`'s own module docstring), and reports aggregate
performance. Mirrors the existing Benchmark History pattern
(`app/api/v1/endpoints/evaluation.py`): `POST .../run`, `GET .../{id}`,
`GET ...` (list, most recent first) — except a backtest runs asynchronously
(`POST /backtests/run` returns once the run is planned and moved to
'running', not once it's finished), the same non-blocking shape
`POST /training-jobs/{id}/run` already established.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.backtest import get_backtest_service, schedule_backtest_run
from app.schemas.backtest import BacktestListResponse, BacktestRunRequest, BacktestRunResponse
from app.services.backtest import BacktestService

router = APIRouter(tags=["backtest"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": (
            "Invalid date range, step, or sort request — including a range that reaches "
            "past the latest actually-stored candle for the requested symbol/timeframe"
        ),
        "content": {
            "application/json": {
                "examples": {
                    "invalid_backtest_range": {
                        "summary": "end is not after start",
                        "value": {
                            "code": "invalid_backtest_range",
                            "detail": "Invalid backtest range: end (...) must be after start (...)",
                        },
                    },
                    "invalid_backtest_step": {
                        "summary": "step is finer than the job's own timeframe",
                        "value": {
                            "code": "invalid_backtest_step",
                            "detail": (
                                "Backtest step '1m' is finer than training job's own "
                                "timeframe '1h' — the step must be the same as, or coarser "
                                "than, the timeframe the model was trained at"
                            ),
                        },
                    },
                    "backtest_range_exceeds_available_data": {
                        "summary": "end reaches past the latest stored candle",
                        "value": {
                            "code": "backtest_range_exceeds_available_data",
                            "detail": (
                                "Requested backtest end (...) is past the latest stored candle "
                                "for this symbol/timeframe (open_time=..., covering data "
                                "through ...) — shrink `end` or wait for more candles to be "
                                "ingested"
                            ),
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown training job, backtest run id, market, or no candles stored yet",
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
                    "backtest_run_not_found": {
                        "summary": "Unknown backtest run id",
                        "value": {
                            "code": "backtest_run_not_found",
                            "detail": "Backtest run 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found",
                        },
                    },
                    "market_not_found": {
                        "summary": "Unknown market symbol",
                        "value": {
                            "code": "market_not_found",
                            "detail": "Market 'ETHUSD' not found",
                        },
                    },
                    "candle_not_found": {
                        "summary": "No candles stored yet for this symbol/timeframe",
                        "value": {
                            "code": "candle_not_found",
                            "detail": "No candles stored for market 'ETHUSD' and timeframe '1h'",
                        },
                    },
                }
            }
        },
    },
}

BacktestServiceDep = Annotated[BacktestService, Depends(get_backtest_service)]
BacktestRunIdPath = Annotated[uuid.UUID, Path(description="Backtest run id")]


@router.post(
    "/backtests/run",
    response_model=BacktestRunResponse,
    summary="Run a backtest over a historical date range",
    description=(
        "Plans the walk (capped at MAX_BACKTEST_STEPS, honestly reporting truncation), "
        "persists the run, and returns immediately with status 'running' — the walk itself "
        "(one live prediction plus an immediate grade, per step, both completely unmodified) "
        "executes in a background task, not before this response is sent. Poll "
        "GET /backtests/{id} while status is 'running'; it settles into 'completed' or "
        "'failed'. No worker/queue service exists yet, so the background task runs in-process "
        "and does not survive an app restart — see ARCHITECTURE.md § 'Backtesting Engine'."
    ),
    responses=_ERROR_RESPONSES,
)
async def run_backtest(
    body: BacktestRunRequest, service: BacktestServiceDep
) -> BacktestRunResponse:
    """Plan, persist, and start a backtest; schedule its walk in the background."""
    response = await service.start(body)
    schedule_backtest_run(uuid.UUID(response.id))
    return response


@router.get(
    "/backtests/{run_id}",
    response_model=BacktestRunResponse,
    summary="Get one backtest run",
    responses=_ERROR_RESPONSES,
)
async def get_backtest(
    run_id: BacktestRunIdPath, service: BacktestServiceDep
) -> BacktestRunResponse:
    """Return one persisted backtest run by id."""
    return await service.get(run_id)


@router.get(
    "/backtests",
    response_model=BacktestListResponse,
    summary="List past backtest runs (Backtest History)",
    description=(
        "Every POST /backtests/run call is recorded, most recent first by default — "
        "filterable by training job, experiment, symbol, or status."
    ),
)
async def list_backtests(
    service: BacktestServiceDep,
    training_job_id: Annotated[
        uuid.UUID | None, Query(description="Only runs for this training job")
    ] = None,
    experiment_id: Annotated[
        uuid.UUID | None, Query(description="Only runs for this experiment")
    ] = None,
    symbol: Annotated[str | None, Query(description="Only runs for this market")] = None,
    status_filter: Annotated[
        str | None, Query(alias="status", description="Exact run status")
    ] = None,
    sort: Annotated[
        str,
        Query(
            description="Sort column; one of symbol, status, created_at, started_at, completed_at"
        ),
    ] = "created_at",
    dir: Annotated[str, Query(description="Sort direction; asc or desc")] = "desc",
    limit: Annotated[
        int,
        Query(ge=1, le=get_settings().backtests_max_limit, description="Maximum runs per page"),
    ] = get_settings().backtests_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of runs to skip")] = 0,
) -> BacktestListResponse:
    """Return a page of past backtest runs matching the given filter/sort criteria."""
    return await service.search(
        training_job_id=training_job_id,
        experiment_id=experiment_id,
        symbol=symbol,
        status_filter=status_filter,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )
