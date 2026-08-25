"""Structural rule tests — required columns and declared data types."""

from dataclasses import replace

from app.dataset_validation.base import ValidationContext
from app.dataset_validation.rules.structural import DataTypesRule, RequiredColumnsRule
from app.features.base import FeatureColumn
from app.features.dataset import DatasetFeatureInfo
from tests.dataset_validation.conftest import make_dataset


class TestRequiredColumnsRule:
    def test_passes_when_every_required_column_is_present(self) -> None:
        dataset = make_dataset(columns=[FeatureColumn(name="close", label="Close")])
        ctx = ValidationContext(dataset=dataset, required_columns=("close",))
        assert RequiredColumnsRule().check(ctx) == []

    def test_flags_a_missing_required_column(self) -> None:
        dataset = make_dataset(columns=[FeatureColumn(name="close", label="Close")])
        ctx = ValidationContext(dataset=dataset, required_columns=("sma_20",))
        issues = RequiredColumnsRule().check(ctx)
        assert len(issues) == 1
        assert issues[0].code == "missing_required_column"
        assert issues[0].column == "sma_20"
        assert issues[0].severity == "error"

    def test_flags_a_feature_declaring_a_column_that_does_not_exist(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="close", label="Close")],
            features=[
                DatasetFeatureInfo(
                    feature="sma",
                    label="SMA",
                    version="1.0.0",
                    params={},
                    columns=["sma_20"],  # not among dataset.columns
                    warmup=20,
                    execution_time_ms=0.1,
                )
            ],
        )
        issues = RequiredColumnsRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "missing_declared_column"
        assert issues[0].column == "sma_20"

    def test_no_required_columns_and_consistent_features_is_clean(self) -> None:
        dataset = make_dataset()
        assert RequiredColumnsRule().check(ValidationContext(dataset=dataset)) == []


class TestDataTypesRule:
    def test_passes_when_every_value_matches_its_dtype(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="close", label="Close", dtype="float")],
            rows=[[100.0], [101.5], [None]],
        )
        assert DataTypesRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_a_string_value_in_a_float_column(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="close", label="Close", dtype="float")],
            rows=[[100.0], ["oops"]],
        )
        issues = DataTypesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "column_dtype_mismatch"
        assert issues[0].column == "close"
        assert issues[0].count == 1

    def test_a_bool_never_passes_as_a_float(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="close", label="Close", dtype="float")],
            rows=[[True]],
        )
        issues = DataTypesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1

    def test_categorical_columns_expect_strings(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="direction", label="Direction", dtype="categorical")],
            rows=[["up"], ["down"], [1.0]],
        )
        issues = DataTypesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].count == 1

    def test_bool_columns_only_accept_bool(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="flag", label="Flag", dtype="bool")],
            rows=[[True], [False], [1]],
        )
        issues = DataTypesRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1

    def test_none_values_are_never_flagged(self) -> None:
        dataset = make_dataset(
            columns=[FeatureColumn(name="close", label="Close", dtype="float")],
            rows=[[None], [None]],
        )
        assert DataTypesRule().check(ValidationContext(dataset=dataset)) == []

    def test_an_unrecognized_dtype_never_flags_anything(self) -> None:
        # Falling through as valid for an unknown/future dtype is deliberate:
        # not recognizing a dtype is not evidence the data itself is wrong.
        column = replace(
            FeatureColumn(name="mystery", label="Mystery", dtype="int"),
            dtype="future_dtype",  # type: ignore[arg-type]
        )
        dataset = make_dataset(columns=[column], rows=[["anything"], [object()]])
        assert DataTypesRule().check(ValidationContext(dataset=dataset)) == []
