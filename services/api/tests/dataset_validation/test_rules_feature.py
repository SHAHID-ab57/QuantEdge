"""Feature-category rule tests — metadata consistency and feature failures."""

from dataclasses import replace

from app.dataset_validation.base import ValidationContext
from app.dataset_validation.rules.feature_rules import FeatureFailureRule, MetadataConsistencyRule
from app.features.quality import FeatureFailure
from tests.dataset_validation.conftest import make_dataset


class TestMetadataConsistencyRule:
    def test_a_well_formed_dataset_has_no_issues(self) -> None:
        dataset = make_dataset()
        assert MetadataConsistencyRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_a_timestamp_row_count_mismatch(self) -> None:
        dataset = make_dataset()
        broken = replace(dataset, timestamps=dataset.timestamps[:-1])
        issues = MetadataConsistencyRule().check(ValidationContext(dataset=broken))
        assert any(issue.code == "row_timestamp_mismatch" for issue in issues)

    def test_flags_a_row_whose_length_does_not_match_the_column_count(self) -> None:
        dataset = make_dataset(rows=[[1.0], [2.0, 3.0], [4.0]])
        issues = MetadataConsistencyRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "row_column_mismatch"
        assert issues[0].row_index == 1

    def test_flags_a_quality_row_count_mismatch(self) -> None:
        dataset = make_dataset(rows_returned=999)
        issues = MetadataConsistencyRule().check(ValidationContext(dataset=dataset))
        assert any(issue.code == "quality_row_count_mismatch" for issue in issues)


class TestFeatureFailureRule:
    def test_no_failures_has_no_issues(self) -> None:
        dataset = make_dataset()
        assert FeatureFailureRule().check(ValidationContext(dataset=dataset)) == []

    def test_surfaces_one_issue_per_failure(self) -> None:
        failures = [
            FeatureFailure(
                feature="ema",
                params={"period": 999},
                error_code="insufficient_data",
                error_detail="Feature 'ema' needs at least 999 candles",
            ),
            FeatureFailure(
                feature="sma",
                params={"period": -1},
                error_code="invalid_feature_parameter",
                error_detail="Feature 'sma': Parameter 'period' must be >= 1, got -1",
            ),
        ]
        dataset = make_dataset(failures=failures)
        issues = FeatureFailureRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 2
        assert {issue.severity for issue in issues} == {"warning"}
        assert {issue.details["error_code"] for issue in issues} == {
            "insufficient_data",
            "invalid_feature_parameter",
        }
        assert any("needs at least 999 candles" in issue.message for issue in issues)
