"""Dependency providers for the dataset validation API."""

import functools
from typing import Annotated

from fastapi import Depends

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.registry import default_registry
from app.dataset_validation.rules import load_builtin_rules
from app.dependencies.features import get_feature_service
from app.services.dataset_validation import DatasetValidationService
from app.services.features import FeatureService


@functools.lru_cache(maxsize=1)
def get_dataset_validator() -> DatasetValidator:
    """Return the process-wide dataset validator.

    Cached for the same reason ``get_feature_pipeline`` is: rule discovery
    only needs to run once per process, and rules are stateless, so one
    instance safely serves every request.
    """
    load_builtin_rules()
    return DatasetValidator(default_registry)


def get_dataset_validation_service(
    feature_service: Annotated[FeatureService, Depends(get_feature_service)],
) -> DatasetValidationService:
    """Build the dataset validation service, wired to the request-scoped feature service."""
    return DatasetValidationService(
        feature_service=feature_service,
        validator=get_dataset_validator(),
    )
