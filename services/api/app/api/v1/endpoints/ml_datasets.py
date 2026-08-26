"""ML Dataset Builder REST endpoints.

Four surfaces, mirroring the Feature Engineering and Dataset Validation
endpoints' own shapes exactly:

- ``GET /ml/targets`` and ``GET /ml/targets/{target}`` publish the target
  registry as a catalogue, the same way ``GET /features`` publishes the
  feature registry.
- ``POST /markets/{symbol}/ml/dataset`` builds, validates, and splits an ML
  dataset, returning it (optionally truncated for preview).
- ``POST /markets/{symbol}/ml/dataset/export`` builds the *same* dataset
  and streams it as a CSV or JSON file.

This is the platform's only supported path for producing a dataset meant
for AI training — see ``ARCHITECTURE.md`` § "ML Dataset Builder" for why
that is a property of *composition* (feature building, target generation,
validation, and splitting all happen together, in a fixed order, every
time) rather than a policy enforced elsewhere.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.dependencies.ml_datasets import get_ml_dataset_service
from app.ml_datasets.export import EXPORT_FORMATS
from app.schemas.ml_datasets import (
    MLDatasetRequest,
    MLDatasetResponse,
    TargetCatalogResponse,
    TargetDTO,
)
from app.services.ml_datasets import MLDatasetService

router = APIRouter(tags=["ml-datasets"])

#: Built from the export registry rather than hardcoded, matching
#: `app.api.v1.endpoints.features`'s identical pattern.
_FORMAT_PATTERN = f"^({'|'.join(EXPORT_FORMATS)})$"

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Invalid parameters, timeframe, range, split ratios, or an unusable dataset",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_split_ratios": {
                        "summary": "Split ratios don't sum to 1.0",
                        "value": {
                            "code": "invalid_split_ratios",
                            "detail": (
                                "Invalid split ratios: train + validation + test must sum to "
                                "1.0, got 1.1 (train=0.7, validation=0.2, test=0.2)"
                            ),
                        },
                    },
                    "duplicate_target_column": {
                        "summary": "Two requested targets (or a target and a feature) collide",
                        "value": {
                            "code": "duplicate_target_column",
                            "detail": (
                                "Column 'next_close_1' would be produced by both 'next_close' "
                                "and 'next_close'; request them with different parameters or "
                                "drop one"
                            ),
                        },
                    },
                    "empty_ml_dataset": {
                        "summary": "Every row was dropped as warmup and/or horizon",
                        "value": {
                            "code": "empty_ml_dataset",
                            "detail": (
                                "Every row was dropped: 30 candles were loaded but the "
                                "requested features need 20 candles of warmup and the "
                                "requested targets need 10 candles of horizon at the end. "
                                "Widen the date range, reduce the largest feature period, or "
                                "reduce the largest target horizon"
                            ),
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown target, unknown market, or no stored candles",
        "content": {
            "application/json": {
                "examples": {
                    "target_not_found": {
                        "summary": "Unknown target name",
                        "value": {
                            "code": "target_not_found",
                            "detail": (
                                "Target 'next_high' is not registered; available: "
                                "next_close, next_direction, next_return"
                            ),
                        },
                    },
                }
            }
        },
    },
}

MLDatasetServiceDep = Annotated[MLDatasetService, Depends(get_ml_dataset_service)]
SymbolPath = Annotated[str, Path(examples=["ETHUSD"], description="Market symbol")]
TargetPath = Annotated[str, Path(examples=["next_close"], description="Registered target name")]


@router.get(
    "/ml/targets",
    response_model=TargetCatalogResponse,
    summary="List available prediction targets",
    description=(
        "Return every registered target generator with its parameter specifications and "
        "output columns. A client can build a complete, correctly-constrained target "
        "selection form from this response alone."
    ),
)
async def list_targets(service: MLDatasetServiceDep) -> TargetCatalogResponse:
    """Return the target catalogue."""
    return service.list_targets()


@router.get(
    "/ml/targets/{target}",
    response_model=TargetDTO,
    summary="Describe one prediction target",
    description="Return a single target generator's metadata, parameters, and output columns.",
    responses=_ERROR_RESPONSES,
)
async def describe_target(target: TargetPath, service: MLDatasetServiceDep) -> TargetDTO:
    """Return one target generator's catalogue entry."""
    return service.get_target(target)


@router.post(
    "/markets/{symbol}/ml/dataset",
    response_model=MLDatasetResponse,
    summary="Build an ML training dataset",
    description=(
        "Build a feature dataset, generate the requested prediction targets over it, run "
        "the Dataset Validation Engine's full rule suite over the assembled matrix, and "
        "split it chronologically into train/validation/test — all in one call, the only "
        "supported path for producing a dataset meant for AI training. Rows still inside "
        "any feature's warmup, or still missing a requested target (no future candle "
        "exists yet to compute it from), are dropped by default. One requested feature or "
        "target failing does not abort the others — it is recorded and the rest of the "
        "dataset still builds, matching the Feature Engineering Engine's own partial-"
        "success contract. A duplicate column between two requests, or invalid split "
        "ratios, still fails the whole request."
    ),
    responses=_ERROR_RESPONSES,
)
async def build_ml_dataset(
    symbol: SymbolPath,
    body: MLDatasetRequest,
    service: MLDatasetServiceDep,
) -> MLDatasetResponse:
    """Build, validate, and split an ML dataset for one market/timeframe/range."""
    return await service.build_dataset(symbol, body)


@router.post(
    "/markets/{symbol}/ml/dataset/export",
    summary="Export an ML dataset as CSV or JSON",
    description=(
        "Build the same dataset as `/ml/dataset` and stream it as a downloadable file — "
        "the full assembled matrix (features and targets as columns) plus a `split` "
        "column naming each row's train/validation/test membership. Always exports the "
        "complete dataset; `preview_rows` is ignored."
    ),
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "description": "The serialized ML dataset as a file download",
            "content": {"text/csv": {}, "application/json": {}},
        },
        **_ERROR_RESPONSES,
    },
)
async def export_ml_dataset(
    symbol: SymbolPath,
    body: MLDatasetRequest,
    service: MLDatasetServiceDep,
    format: Annotated[
        str,
        Query(
            pattern=_FORMAT_PATTERN,
            description=f"Export format: one of {', '.join(sorted(EXPORT_FORMATS))}",
        ),
    ] = "csv",
) -> Response:
    """Export a complete ML dataset as a downloadable file."""
    exported = await service.export_dataset(symbol, body, format)
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )
