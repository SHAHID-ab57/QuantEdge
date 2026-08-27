"""Tests for `app/training/error_reporting.py`'s `describe_training_failure`."""

from app.training.error_reporting import describe_training_failure
from app.training.errors import (
    MissingTrainingDataSourceError,
    NoNumericFeatureColumnsError,
    UndefinedFeatureValueError,
)


class TestDescribeTrainingFailure:
    def test_reports_the_affected_feature_and_row_for_undefined_feature_value(self) -> None:
        report = describe_training_failure(UndefinedFeatureValueError("sma_20", row_index=7))

        assert report["affected_feature"] == "sma_20"
        assert report["affected_rows"] == [7]
        assert "undefined or non-numeric" in report["reason"]
        assert "upstream feature generator" in report["suggested_fix"]

    def test_omits_affected_feature_and_rows_when_the_error_carries_none(self) -> None:
        report = describe_training_failure(NoNumericFeatureColumnsError())

        assert report["affected_feature"] is None
        assert report["affected_rows"] is None
        assert "categorical feature" in report["suggested_fix"]

    def test_looks_up_a_known_suggested_fix_by_error_code(self) -> None:
        report = describe_training_failure(MissingTrainingDataSourceError())

        assert report["suggested_fix"] == (
            "Set both symbol and timeframe on this job before running it."
        )

    def test_falls_back_to_a_default_suggested_fix_for_an_unrecognized_exception(self) -> None:
        report = describe_training_failure(ValueError("some other unrelated failure"))

        assert report["reason"] == "some other unrelated failure"
        assert report["suggested_fix"] == (
            "Review the job's logs for the exact stage and error, then retry."
        )
