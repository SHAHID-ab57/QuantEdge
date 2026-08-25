"""Feature engineering REST endpoints.

Three surfaces:

- ``GET /features`` and ``GET /features/{feature}`` publish the registry as
  a catalogue, including each generator's parameter specs, so a client can
  build a correct input form without hardcoding anything about any specific
  feature.
- ``POST /markets/{symbol}/features/dataset`` builds a dataset and returns
  it (optionally truncated for preview).
- ``POST /markets/{symbol}/features/export`` builds the *same* dataset and
  streams it as a CSV or JSON file.

Export is a separate endpoint rather than a ``format`` parameter on the
dataset endpoint because the two differ in more than encoding: the preview
may be truncated and the export never is. Conflating them is how a
researcher ends up training on the 200 rows they happened to see.

Parameters arrive in a JSON body rather than the query string (unlike the
indicator endpoints) because a dataset request is inherently a *list* of
feature/parameter pairs, which a flat query string cannot express without
inventing an encoding.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.dependencies.features import get_feature_service
from app.features.export import EXPORT_FORMATS
from app.schemas.features import (
    FeatureCatalogResponse,
    FeatureDatasetRequest,
    FeatureDatasetResponse,
    FeatureDTO,
)
from app.services.features import FeatureService

router = APIRouter(tags=["features"])

#: Built from the export registry rather than hardcoded, so a future
#: Parquet entry in `EXPORT_FORMATS` is immediately acceptable here too.
_FORMAT_PATTERN = f"^({'|'.join(EXPORT_FORMATS)})$"

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Invalid parameters, timeframe, range, or an unusable dataset",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_feature_parameter": {
                        "summary": "Parameter out of range, unknown, or wrong type",
                        "value": {
                            "code": "invalid_feature_parameter",
                            "detail": "Feature 'sma': Parameter 'period' must be >= 1, got 0",
                        },
                    },
                    "duplicate_feature_column": {
                        "summary": "Two requested features produce the same column",
                        "value": {
                            "code": "duplicate_feature_column",
                            "detail": (
                                "Column 'sma_20' would be produced by both 'sma' and "
                                "'sma'; request them with different parameters or drop one"
                            ),
                        },
                    },
                    "empty_dataset": {
                        "summary": "Every row was dropped as warmup",
                        "value": {
                            "code": "empty_dataset",
                            "detail": (
                                "Every row was dropped: 30 candles were loaded but the "
                                "requested features need 50 candles of warmup. Widen the "
                                "date range or reduce the largest period parameter"
                            ),
                        },
                    },
                    "missing_feature_dependency": {
                        "summary": "A requested feature's dependency wasn't also requested",
                        "value": {
                            "code": "missing_feature_dependency",
                            "detail": (
                                "Feature 'bollinger_width' depends on 'sma', which was not "
                                "included in this request. Add it to `features` alongside "
                                "this one."
                            ),
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown feature, unknown market, or no stored candles",
        "content": {
            "application/json": {
                "examples": {
                    "feature_not_found": {
                        "summary": "Unknown feature name",
                        "value": {
                            "code": "feature_not_found",
                            "detail": (
                                "Feature 'macd' is not registered; available: "
                                "candle_shape, ema, ohlcv, sma, wma"
                            ),
                        },
                    },
                    "market_not_found": {
                        "summary": "Unknown market symbol",
                        "value": {"code": "market_not_found", "detail": "Market 'NOPE' not found"},
                    },
                }
            }
        },
    },
}

FeatureServiceDep = Annotated[FeatureService, Depends(get_feature_service)]
SymbolPath = Annotated[str, Path(examples=["ETHUSD"], description="Market symbol")]
FeaturePath = Annotated[str, Path(examples=["sma"], description="Registered feature name")]


@router.get(
    "/features",
    response_model=FeatureCatalogResponse,
    summary="List available feature generators",
    description=(
        "Return every registered feature generator with its parameter "
        "specifications and output columns. A client can build a complete, "
        "correctly-constrained selection form from this response alone."
    ),
)
async def list_features(service: FeatureServiceDep) -> FeatureCatalogResponse:
    """Return the feature catalogue."""
    return service.list_features()


@router.get(
    "/features/{feature}",
    response_model=FeatureDTO,
    summary="Describe one feature generator",
    description="Return a single generator's metadata, parameters, and output columns.",
    responses=_ERROR_RESPONSES,
)
async def describe_feature(feature: FeaturePath, service: FeatureServiceDep) -> FeatureDTO:
    """Return one generator's catalogue entry."""
    return service.get_feature(feature)


@router.post(
    "/markets/{symbol}/features/dataset",
    response_model=FeatureDatasetResponse,
    summary="Build a feature dataset",
    description=(
        "Run several feature generators over one market/timeframe/range and "
        "return the assembled matrix: one timestamped row per candle, one "
        "column per feature output. Rows still inside any feature's warmup "
        "are dropped by default (a training matrix must not contain nulls) "
        "and the count removed is reported in `meta.rows_dropped`. Set "
        "`preview_rows` to cap the response for display — `meta.total_rows` "
        "and `meta.truncated` always describe the full dataset. One "
        "requested feature failing (a bad parameter, an under-sized range "
        "for that feature alone) does not abort the others — it is recorded "
        "in `quality.feature_failures` and the rest of the dataset still "
        "builds, mirroring the indicator batch endpoint's partial-success "
        "contract. A missing feature dependency or a column collision "
        "between two requested features still fails the whole request, "
        "since neither has a partial result that would make sense."
    ),
    responses=_ERROR_RESPONSES,
)
async def build_feature_dataset(
    symbol: SymbolPath,
    body: FeatureDatasetRequest,
    service: FeatureServiceDep,
) -> FeatureDatasetResponse:
    """Build a feature dataset for one market/timeframe/range."""
    return await service.build_dataset(symbol, body)


@router.post(
    "/markets/{symbol}/features/export",
    summary="Export a feature dataset as CSV or JSON",
    description=(
        "Build the same dataset as `/features/dataset` and stream it as a "
        "downloadable file. Always exports the **complete** dataset — "
        "`preview_rows` is ignored here, since an export truncated to what a "
        "preview happened to show would silently produce a partial training "
        "set. Both formats carry the pipeline version, every feature's "
        "resolved parameters, and its version, so the file is reproducible."
    ),
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "description": "The serialized dataset as a file download",
            "content": {"text/csv": {}, "application/json": {}},
        },
        **_ERROR_RESPONSES,
    },
)
async def export_feature_dataset(
    symbol: SymbolPath,
    body: FeatureDatasetRequest,
    service: FeatureServiceDep,
    format: Annotated[
        str,
        Query(
            pattern=_FORMAT_PATTERN,
            description=f"Export format: one of {', '.join(sorted(EXPORT_FORMATS))}",
        ),
    ] = "csv",
) -> Response:
    """Export a complete feature dataset as a downloadable file."""
    exported = await service.export_dataset(symbol, body, format)
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )
