"""Data quality rule tests — missing values, duplicate rows/timestamps, NaN, infinity."""

from datetime import UTC, datetime, timedelta

from app.dataset_validation.base import ValidationContext
from app.dataset_validation.rules.data_quality import (
    DuplicateRowsRule,
    DuplicateTimestampsRule,
    InfiniteValuesRule,
    MissingValuesRule,
    NaNValuesRule,
)
from app.features.base import FeatureColumn
from tests.dataset_validation.conftest import make_dataset


class TestMissingValuesRule:
    def test_clean_dataset_has_no_issues(self) -> None:
        dataset = make_dataset(rows=[[1.0], [2.0], [3.0]])
        assert MissingValuesRule().check(ValidationContext(dataset=dataset)) == []

    def test_counts_nulls_per_column(self) -> None:
        dataset = make_dataset(rows=[[1.0], [None], [None]])
        issues = MissingValuesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].code == "missing_values"
        assert issues[0].count == 2
        assert issues[0].column == "close"

    def test_only_flags_columns_that_actually_have_nulls(self) -> None:
        columns = [
            FeatureColumn(name="close", label="Close"),
            FeatureColumn(name="volume", label="Volume"),
        ]
        dataset = make_dataset(columns=columns, rows=[[1.0, 10.0], [None, 20.0]])
        issues = MissingValuesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].column == "close"


class TestDuplicateRowsRule:
    def test_clean_dataset_has_no_issues(self) -> None:
        dataset = make_dataset(rows=[[1.0], [2.0], [3.0]])
        assert DuplicateRowsRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_exact_duplicate_rows(self) -> None:
        dataset = make_dataset(rows=[[1.0], [1.0], [2.0]])
        issues = DuplicateRowsRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "duplicate_rows"
        assert issues[0].count == 1
        assert issues[0].severity == "warning"

    def test_three_identical_rows_count_as_two_duplicates(self) -> None:
        dataset = make_dataset(rows=[[1.0], [1.0], [1.0]])
        issues = DuplicateRowsRule().check(ValidationContext(dataset=dataset))
        assert issues[0].count == 2

    def test_multi_column_rows_must_match_on_every_column(self) -> None:
        columns = [
            FeatureColumn(name="close", label="Close"),
            FeatureColumn(name="volume", label="Volume"),
        ]
        dataset = make_dataset(columns=columns, rows=[[1.0, 10.0], [1.0, 20.0]])
        assert DuplicateRowsRule().check(ValidationContext(dataset=dataset)) == []


class TestDuplicateTimestampsRule:
    def test_clean_dataset_has_no_issues(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        timestamps = [base, base + timedelta(hours=1), base + timedelta(hours=2)]
        dataset = make_dataset(timestamps=timestamps, rows=[[1.0], [2.0], [3.0]])
        assert DuplicateTimestampsRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_a_repeated_timestamp(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        dataset = make_dataset(timestamps=[base, base, base], rows=[[1.0], [2.0], [3.0]])
        issues = DuplicateTimestampsRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "duplicate_timestamps"
        assert issues[0].severity == "error"
        assert issues[0].count == 2  # three occurrences == two extras


class TestNaNValuesRule:
    def test_clean_dataset_has_no_issues(self) -> None:
        dataset = make_dataset(rows=[[1.0], [2.0]])
        assert NaNValuesRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_nan_distinctly_from_none(self) -> None:
        dataset = make_dataset(rows=[[float("nan")], [None], [1.0]])
        issues = NaNValuesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "nan_values"
        assert issues[0].count == 1
        assert issues[0].severity == "error"

    def test_none_alone_never_triggers_this_rule(self) -> None:
        dataset = make_dataset(rows=[[None], [None]])
        assert NaNValuesRule().check(ValidationContext(dataset=dataset)) == []


class TestInfiniteValuesRule:
    def test_clean_dataset_has_no_issues(self) -> None:
        dataset = make_dataset(rows=[[1.0], [2.0]])
        assert InfiniteValuesRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_positive_and_negative_infinity(self) -> None:
        dataset = make_dataset(rows=[[float("inf")], [float("-inf")], [1.0]])
        issues = InfiniteValuesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "infinite_values"
        assert issues[0].count == 2
        assert issues[0].severity == "error"

    def test_nan_never_triggers_this_rule(self) -> None:
        dataset = make_dataset(rows=[[float("nan")]])
        assert InfiniteValuesRule().check(ValidationContext(dataset=dataset)) == []
