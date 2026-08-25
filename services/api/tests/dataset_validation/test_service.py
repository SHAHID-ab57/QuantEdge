"""Dataset validation service tests — delegation to `FeatureService.build_raw` and the engine.

Uses a stub in place of a real ``FeatureService`` (which needs a database
session) so this file tests exactly one thing in isolation: that
``DatasetValidationService`` builds via the shared path and hands the
result, plus the caller's ``required_columns``/``rules``, to the engine
unchanged. End-to-end coverage against a real database lives in
``tests/api/test_dataset_validation_api.py``.
"""

from dataclasses import dataclass

import pytest

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.registry import default_registry
from app.dataset_validation.rules import load_builtin_rules
from app.schemas.dataset_validation import DatasetValidationRequest
from app.schemas.features import FeatureRequestItem
from app.services.dataset_validation import DatasetValidationService
from tests.dataset_validation.conftest import make_dataset


@dataclass
class _StubFeatureService:
    """Records the request it was called with and returns a canned dataset."""

    dataset: object
    calls: list[tuple[str, object]]

    async def build_raw(self, symbol: str, request: object) -> tuple[object, float]:
        self.calls.append((symbol, request))
        return self.dataset, 1.0


@pytest.fixture(scope="module")
def validator() -> DatasetValidator:
    load_builtin_rules()
    return DatasetValidator(default_registry)


def request_body(**overrides: object) -> DatasetValidationRequest:
    defaults: dict[str, object] = {
        "timeframe": "1h",
        "features": [FeatureRequestItem(feature="ohlcv")],
    }
    defaults.update(overrides)
    return DatasetValidationRequest(**defaults)


class TestValidateDataset:
    async def test_builds_via_the_shared_feature_service_path(
        self, validator: DatasetValidator
    ) -> None:
        stub = _StubFeatureService(dataset=make_dataset(), calls=[])
        service = DatasetValidationService(feature_service=stub, validator=validator)
        body = request_body()
        await service.validate_dataset("ETHUSD", body)
        assert stub.calls == [("ETHUSD", body)]

    async def test_returns_a_report_for_the_built_dataset(
        self, validator: DatasetValidator
    ) -> None:
        dataset = make_dataset(dataset_id="abc123")
        stub = _StubFeatureService(dataset=dataset, calls=[])
        service = DatasetValidationService(feature_service=stub, validator=validator)
        report = await service.validate_dataset("ETHUSD", request_body())
        assert report.dataset_id == "abc123"

    async def test_forwards_required_columns_to_the_engine(
        self, validator: DatasetValidator
    ) -> None:
        stub = _StubFeatureService(dataset=make_dataset(), calls=[])
        service = DatasetValidationService(feature_service=stub, validator=validator)
        report = await service.validate_dataset("ETHUSD", request_body(required_columns=["sma_20"]))
        assert any(issue.code == "missing_required_column" for issue in report.issues)

    async def test_forwards_a_rule_subset_to_the_engine(self, validator: DatasetValidator) -> None:
        stub = _StubFeatureService(dataset=make_dataset(), calls=[])
        service = DatasetValidationService(feature_service=stub, validator=validator)
        report = await service.validate_dataset("ETHUSD", request_body(rules=["required_columns"]))
        assert report.rules_run == ("required_columns",)


class TestListRules:
    def test_lists_every_registered_rule(self, validator: DatasetValidator) -> None:
        stub = _StubFeatureService(dataset=make_dataset(), calls=[])
        service = DatasetValidationService(feature_service=stub, validator=validator)
        catalogue = service.list_rules()
        assert catalogue.total == len(validator.registry)
        assert {rule.name for rule in catalogue.rules} == set(validator.registry.names())

    def test_reports_distinct_categories(self, validator: DatasetValidator) -> None:
        stub = _StubFeatureService(dataset=make_dataset(), calls=[])
        service = DatasetValidationService(feature_service=stub, validator=validator)
        catalogue = service.list_rules()
        assert {"structural", "data_quality", "time_series", "feature"} <= set(catalogue.categories)
