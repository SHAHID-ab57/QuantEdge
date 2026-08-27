"""Tests for `build_training_dataset` — the bridge from a real `MLDataset` to a
`TrainingDataset` a real model adapter can train on."""

import pytest

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.registry import default_registry as rule_registry
from app.dataset_validation.rules import load_builtin_rules
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry as feature_registry
from app.ml_datasets.dataset import MLDatasetBuilder, TargetRequest
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import default_registry as target_registry
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from app.training.dataset_loader import build_training_dataset
from app.training.errors import (
    EmptyTrainingSplitError,
    IncompatibleTargetDtypeError,
    NoNumericFeatureColumnsError,
    NoTargetColumnsError,
    UndefinedFeatureValueError,
    UnknownTargetColumnError,
)
from tests.ml_datasets.conftest import candles


@pytest.fixture(scope="module")
def builder() -> MLDatasetBuilder:
    load_builtin_features()
    load_builtin_rules()
    load_builtin_targets()
    return MLDatasetBuilder(
        feature_builder=FeatureDatasetBuilder(FeaturePipeline(feature_registry)),
        target_pipeline=TargetPipeline(target_registry),
        validator=DatasetValidator(rule_registry),
        splitter=ChronologicalSplitter(),
    )


class TestBuildTrainingDataset:
    def test_builds_train_validation_test_matrices_for_a_regression_target(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml_dataset = builder.build(
            "ETHUSD", "1h", candles(100), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )

        dataset = build_training_dataset(ml_dataset, model_kind="regression")

        assert dataset.target_column == "next_close_1"
        assert dataset.feature_columns == ("open", "high", "low", "close", "volume")
        assert dataset.train is not None
        assert dataset.validation is not None
        assert dataset.test is not None
        assert len(dataset.train.X) > 0
        assert len(dataset.train.X) == len(dataset.train.y)
        assert all(len(row) == len(dataset.feature_columns) for row in dataset.train.X)

    def test_builds_a_classification_target_with_string_labels(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(100),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_direction")],
        )

        dataset = build_training_dataset(ml_dataset, model_kind="classification")

        assert dataset.target_column == "next_direction_1"
        assert all(isinstance(value, str) for value in dataset.train.y)

    def test_defaults_to_the_first_target_column_when_none_is_given(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(100),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close"), TargetRequest("next_return")],
        )

        dataset = build_training_dataset(ml_dataset, model_kind="regression", target_column=None)

        assert dataset.target_column == ml_dataset.target_columns[0]

    def test_honors_an_explicit_target_column_override(self, builder: MLDatasetBuilder) -> None:
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(100),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close"), TargetRequest("next_return")],
        )
        second_target = ml_dataset.target_columns[1]

        dataset = build_training_dataset(
            ml_dataset, model_kind="regression", target_column=second_target
        )

        assert dataset.target_column == second_target

    def test_raises_for_an_unknown_target_column_override(self, builder: MLDatasetBuilder) -> None:
        ml_dataset = builder.build(
            "ETHUSD", "1h", candles(100), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )

        with pytest.raises(UnknownTargetColumnError):
            build_training_dataset(
                ml_dataset, model_kind="regression", target_column="not_a_column"
            )

    def test_raises_when_the_dataset_has_no_target_columns(self, builder: MLDatasetBuilder) -> None:
        ml_dataset = builder.build(
            "ETHUSD", "1h", candles(100), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        # Simulate "no targets survived" by emptying the field directly — the builder
        # itself never actually produces this shape when at least one target is
        # requested and resolves, but the loader must still guard against it.
        from dataclasses import replace

        empty = replace(ml_dataset, target_columns=())

        with pytest.raises(NoTargetColumnsError):
            build_training_dataset(empty, model_kind="regression")

    def test_raises_for_a_regression_adapter_over_a_categorical_target(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(100),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_direction")],
        )

        with pytest.raises(IncompatibleTargetDtypeError):
            build_training_dataset(ml_dataset, model_kind="regression")

    def test_raises_when_no_feature_column_is_numeric(self, builder: MLDatasetBuilder) -> None:
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(100),
            [FeatureRequest("candle_shape")],
            [TargetRequest("next_close")],
        )
        # `candle_shape` produces body/upper_wick/lower_wick (float) *and*
        # candle_direction (categorical) — force every *feature* column (never the
        # target column) categorical, to exercise the "nothing numeric survives"
        # path directly without tripping the dtype-compatibility check first.
        from dataclasses import replace

        categorical_columns = [
            replace(c, dtype="categorical") if c.name in ml_dataset.feature_columns else c
            for c in ml_dataset.dataset.columns
        ]
        stripped = replace(
            ml_dataset, dataset=replace(ml_dataset.dataset, columns=categorical_columns)
        )

        with pytest.raises(NoNumericFeatureColumnsError):
            build_training_dataset(stripped, model_kind="regression")

    def test_raises_when_a_numeric_feature_column_unexpectedly_holds_none(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml_dataset = builder.build(
            "ETHUSD", "1h", candles(100), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        # `drop_warmup`/`drop_undefined_targets` (both default `True`) guarantee this
        # never happens in practice — simulate it anyway, in the *split* rows the
        # loader actually reads, to prove it reports a named domain error instead
        # of an opaque `TypeError` if it ever did.
        from dataclasses import replace

        broken_rows = [list(row) for row in ml_dataset.split.train.rows]
        broken_rows[0][0] = None
        broken_train = replace(ml_dataset.split.train, rows=broken_rows)
        stripped = replace(ml_dataset, split=replace(ml_dataset.split, train=broken_train))

        with pytest.raises(UndefinedFeatureValueError):
            build_training_dataset(stripped, model_kind="regression")

    def test_raises_when_a_split_has_zero_rows(self, builder: MLDatasetBuilder) -> None:
        # Two candles, horizon 1 -> exactly one usable row, which an 0.7/0.15/0.15
        # split leaves entirely in train, leaving validation empty.
        ml_dataset = builder.build(
            "ETHUSD", "1h", candles(2), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )

        with pytest.raises(EmptyTrainingSplitError):
            build_training_dataset(ml_dataset, model_kind="regression")
