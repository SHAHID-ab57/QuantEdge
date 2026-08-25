"""Dataset validation service — the bridge between a built dataset and the validation engine.

Builds nothing itself: it reuses ``FeatureService.build_raw`` to get the
exact same ``FeatureDataset`` that ``/features/dataset`` and
``/features/export`` already build (identical candle loading, warmup
widening, and partial-success feature generation), then hands it to
``DatasetValidator``. No dataset-building logic is duplicated here — the
whole point of this service is that validation runs *after* the same
pipeline everything else already goes through, never a second, parallel
path that could quietly drift from it.
"""

from dataclasses import dataclass

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.report import ValidationReport
from app.schemas.dataset_validation import (
    DatasetValidationRequest,
    ValidationRuleCatalogResponse,
    ValidationRuleDTO,
)
from app.services.features import FeatureService


@dataclass(frozen=True)
class DatasetValidationService:
    """Business logic for the dataset validation REST API."""

    feature_service: FeatureService
    validator: DatasetValidator

    async def validate_dataset(
        self, symbol: str, request: DatasetValidationRequest
    ) -> ValidationReport:
        """Build a dataset for one market/timeframe/range and validate it.

        ``request`` is a ``FeatureDatasetRequest`` plus ``required_columns``
        and ``rules`` — everything ``FeatureService.build_raw`` needs is
        already on it, since ``DatasetValidationRequest`` subclasses that
        request type rather than wrapping or duplicating it.
        """
        dataset, _ = await self.feature_service.build_raw(symbol, request)
        return self.validator.validate(
            dataset,
            required_columns=tuple(request.required_columns),
            rules=tuple(request.rules) if request.rules is not None else None,
        )

    def list_rules(self) -> ValidationRuleCatalogResponse:
        """Return the full validation rule catalogue.

        Reads straight from the registry, so a rule added to
        ``app/dataset_validation/rules/`` appears here with no change to
        this service.
        """
        metadata = self.validator.registry.describe_all()
        rules = [ValidationRuleDTO.from_metadata(entry) for entry in metadata]
        categories = sorted({entry.category for entry in metadata})
        return ValidationRuleCatalogResponse(
            rules=rules,
            total=len(rules),
            categories=categories,
        )
