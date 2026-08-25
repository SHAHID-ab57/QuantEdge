"""Dataset validation REST endpoints.

Two surfaces:

- ``POST /markets/{symbol}/features/validate`` builds a dataset — the
  exact same one ``/features/dataset`` and ``/features/export`` build, via
  ``FeatureService.build_raw`` — and runs the validation engine's
  registered rules over it, returning a structured JSON report. This is
  deliberately not a third way to build a dataset: the body is
  ``DatasetValidationRequest``, a ``FeatureDatasetRequest`` plus two
  optional validation-only fields (``required_columns``, ``rules``), so
  the exact same market/timeframe/range/feature-selection request that
  builds a dataset also validates it.
- ``GET /validation/rules`` publishes the rule registry as a catalogue,
  mirroring ``GET /features`` and ``GET /indicators``, so a client can
  render which checks exist (name, category, description, default
  severity) without hardcoding anything about any specific rule.

Mounted under ``/markets/{symbol}/features/...`` rather than a new
``/datasets/...`` namespace, matching the existing sibling endpoints
(``/features/dataset``, ``/features/export``) this route sits beside —
one dataset-related namespace, not two.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, status

from app.dependencies.dataset_validation import get_dataset_validation_service
from app.schemas.dataset_validation import (
    DatasetValidationRequest,
    ValidationReportResponse,
    ValidationRuleCatalogResponse,
)
from app.services.dataset_validation import DatasetValidationService

router = APIRouter(tags=["dataset-validation"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown market, unknown feature, or an unregistered validation rule",
        "content": {
            "application/json": {
                "examples": {
                    "validation_rule_not_found": {
                        "summary": "An unknown rule name was requested via `rules`",
                        "value": {
                            "code": "validation_rule_not_found",
                            "detail": (
                                "Validation rule 'made_up_rule' is not registered; available: "
                                "data_types, duplicate_rows, duplicate_timestamps, "
                                "feature_failures, infinite_values, metadata_consistency, "
                                "missing_values, nan_values, required_columns, "
                                "time_gaps, timestamp_ordering"
                            ),
                        },
                    },
                }
            }
        },
    },
}

SymbolPath = Annotated[str, Path(examples=["ETHUSD"], description="Market symbol")]
DatasetValidationServiceDep = Annotated[
    DatasetValidationService, Depends(get_dataset_validation_service)
]


@router.post(
    "/markets/{symbol}/features/validate",
    response_model=ValidationReportResponse,
    summary="Validate a feature dataset",
    description=(
        "Build a dataset — the same one `/features/dataset` builds — and run "
        "every registered validation rule over it (structural, data quality, "
        "time-series, and feature checks), returning a structured report. "
        "`passed` is false only when at least one `error`-severity issue was "
        "found; `warning`/`info` issues are always reported but never fail "
        "the gate. Pass `required_columns` to additionally require specific "
        "columns, or `rules` to run only a named subset — see "
        "`GET /validation/rules` for the full catalogue."
    ),
    responses=_ERROR_RESPONSES,
)
async def validate_feature_dataset(
    symbol: SymbolPath,
    body: DatasetValidationRequest,
    service: DatasetValidationServiceDep,
) -> ValidationReportResponse:
    """Build and validate a feature dataset, returning a structured quality report."""
    report = await service.validate_dataset(symbol, body)
    return ValidationReportResponse.from_report(report)


@router.get(
    "/validation/rules",
    response_model=ValidationRuleCatalogResponse,
    summary="List available validation rules",
    description=(
        "Return every registered validation rule with its category, description, "
        "and default severity. A client can build a rule-selection UI from this "
        "response alone, exactly as `GET /features` already does for generators."
    ),
)
async def list_validation_rules(
    service: DatasetValidationServiceDep,
) -> ValidationRuleCatalogResponse:
    """Return the validation rule catalogue."""
    return service.list_rules()
