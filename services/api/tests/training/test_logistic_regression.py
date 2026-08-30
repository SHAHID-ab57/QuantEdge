"""Tests for `LogisticRegressionAdapter` — a real scikit-learn baseline classifier."""

from pathlib import Path

import pytest

import app.training.adapters.logistic_regression as logistic_regression_module
from app.features.ai_extensions import NormalizationStats
from app.training.adapters.logistic_regression import LogisticRegressionAdapter
from app.training.base import SplitMatrix, TrainingDataset
from app.training.errors import TrainingExecutionError
from app.training.normalization import apply_normalization
from app.training.serialization import LocalDiskModelSerializer


def make_dataset() -> TrainingDataset:
    # Deterministic, perfectly separable-by-sign data: label is "pos" when the
    # single feature is positive, "neg" otherwise — a baseline classifier should
    # learn this trivially, so metrics are exact and reproducible.
    train_x = [[float(i)] for i in range(-10, 10)]
    train_y = ["pos" if x[0] > 0 else "neg" for x in train_x]
    validation_x = [[5.0], [-5.0], [3.0], [-3.0]]
    validation_y = ["pos", "neg", "pos", "neg"]
    test_x = [[1.0], [-1.0]]
    test_y = ["pos", "neg"]
    return TrainingDataset(
        dataset_version="ds-test",
        feature_columns=("x",),
        target_column="label",
        train=SplitMatrix(X=train_x, y=train_y),
        validation=SplitMatrix(X=validation_x, y=validation_y),
        test=SplitMatrix(X=test_x, y=test_y),
    )


@pytest.fixture(autouse=True)
def _local_serializer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirects the adapter module's `default_serializer` to a throwaway directory,
    so every test in this file writes/reads joblib artifacts under `tmp_path`
    instead of the process-wide `Settings.model_artifact_dir`."""
    monkeypatch.setattr(
        logistic_regression_module, "default_serializer", LocalDiskModelSerializer(tmp_path)
    )


class TestInitialize:
    def test_accepts_valid_hyperparameters(self) -> None:
        LogisticRegressionAdapter().initialize({"max_iter": 100, "C": 0.5, "random_seed": 1})

    def test_uses_defaults_when_omitted(self) -> None:
        LogisticRegressionAdapter().initialize({})


class TestTrain:
    def test_raises_when_no_real_data_is_loaded(self) -> None:
        adapter = LogisticRegressionAdapter()
        with pytest.raises(TrainingExecutionError):
            adapter.train(TrainingDataset(dataset_version="ds-1"), {})

    def test_wraps_a_scikit_learn_fit_failure_as_a_training_execution_error(self) -> None:
        adapter = LogisticRegressionAdapter()
        broken = TrainingDataset(
            dataset_version="ds-1",
            feature_columns=("x",),
            target_column="label",
            # Mismatched X/y row counts — scikit-learn raises ValueError on `.fit`.
            train=SplitMatrix(X=[[1.0], [2.0]], y=["pos"]),
            validation=SplitMatrix(X=[[1.0]], y=["pos"]),
        )

        with pytest.raises(TrainingExecutionError):
            adapter.train(broken, {})

    def test_trains_and_reports_perfect_metrics_on_separable_data(self) -> None:
        adapter = LogisticRegressionAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 200})

        assert result.metrics["accuracy"] == pytest.approx(1.0)
        assert result.metrics["f1"] == pytest.approx(1.0)
        assert result.artifact_uri.startswith("file://")
        assert set(result.summary["classes"]) == {"neg", "pos"}
        assert result.summary["target_column"] == "label"
        assert result.summary["feature_columns"] == ["x"]
        assert result.summary["n_train"] == 20
        assert result.summary["n_validation"] == 4
        assert result.summary["n_test"] == 2
        assert "confusion_matrix" in result.summary
        assert "test_metrics" in result.summary
        assert result.summary["test_metrics"]["accuracy"] == pytest.approx(1.0)

    def test_hyperparameters_are_recorded_in_the_summary(self) -> None:
        adapter = LogisticRegressionAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 50, "C": 2.0, "random_seed": 7})

        assert result.summary["hyperparameters"] == {"max_iter": 50, "C": 2.0, "random_seed": 7}


class TestPredict:
    def test_loads_the_saved_model_and_predicts(self) -> None:
        adapter = LogisticRegressionAdapter()
        result = adapter.train(make_dataset(), {})

        predictions = adapter.predict(result.artifact_uri, [[5.0], [-5.0]])

        assert predictions == ["pos", "neg"]


def _make_scale_biased_dataset() -> tuple[list[list[float]], list[str]]:
    """Two features, `big` (scale ~1000) and `small` (scale ~1), each carrying
    the *entire* real signal for exactly one disjoint half of the rows —
    genuinely independent (never collinear), equally informative overall, at
    a 1000x scale difference. The concrete construction this platform's own
    scale-bias bug (Feature Importance ranking `candle_body` above `close`
    purely from scale) actually produces: on raw data, whichever feature is
    active at the *smaller* scale needs a proportionally larger coefficient
    to matter — so it ranks as "more important" by raw |coefficient| alone,
    even though both halves are equally informative by construction.
    """
    # First half: only "big" carries signal (small is uninformative/zero here).
    first_half = [
        ([1000.0 if i % 2 == 0 else -1000.0, 0.0], "pos" if i % 2 == 0 else "neg")
        for i in range(20)
    ]
    # Second half: only "small" carries signal (big is uninformative/zero here).
    second_half = [
        ([0.0, 1.0 if i % 2 == 0 else -1.0], "pos" if i % 2 == 0 else "neg") for i in range(20)
    ]
    rows = first_half + second_half
    X = [row[0] for row in rows]  # noqa: N806
    y = [row[1] for row in rows]
    return X, y


class TestFeatureImportanceScaleBias:
    """The acceptance-criteria "concrete proof": normalizing before training
    measurably changes Feature Importance's relative ranking on the identical
    underlying dataset+model, because raw coefficients are scale-biased and
    normalized ones are not."""

    def test_normalizing_corrects_the_scale_bias_between_differently_scaled_features(
        self,
    ) -> None:
        train_x, train_y = _make_scale_biased_dataset()
        validation_x = [[1000.0, 0.0], [-1000.0, 0.0], [0.0, 1.0], [0.0, -1.0]]
        validation_y = ["pos", "neg", "pos", "neg"]

        raw_dataset = TrainingDataset(
            dataset_version="ds-raw",
            feature_columns=("big", "small"),
            target_column="label",
            train=SplitMatrix(X=train_x, y=train_y),
            validation=SplitMatrix(X=validation_x, y=validation_y),
        )
        raw_result = LogisticRegressionAdapter().train(raw_dataset, {})
        raw_importance = {
            row["feature"]: row["abs_importance"]
            for row in raw_result.summary["feature_importance"]
        }
        # Every raw row must say plainly it is *not* scale-comparable.
        assert all(row["normalized"] is False for row in raw_result.summary["feature_importance"])
        assert raw_result.summary["normalization"] is None

        # Fit real z-score stats on the train split alone (mean is 0 for both
        # columns by this dataset's own symmetric construction; std differs by
        # exactly the 1000x scale) and apply the identical transform to train
        # and validation alike — precisely what `build_training_dataset` does.
        big_values = [row[0] for row in train_x]
        small_values = [row[1] for row in train_x]

        def population_std(values: list[float]) -> float:
            mean = sum(values) / len(values)
            return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5

        stats = [
            NormalizationStats(column="big", mean=0.0, std=population_std(big_values)),
            NormalizationStats(column="small", mean=0.0, std=population_std(small_values)),
        ]
        normalized_dataset = TrainingDataset(
            dataset_version="ds-normalized",
            feature_columns=("big", "small"),
            target_column="label",
            train=SplitMatrix(X=apply_normalization(train_x, stats), y=train_y),
            validation=SplitMatrix(X=apply_normalization(validation_x, stats), y=validation_y),
            normalization=stats,
            normalization_method="zscore",
        )
        normalized_result = LogisticRegressionAdapter().train(normalized_dataset, {})
        normalized_importance = {
            row["feature"]: row["abs_importance"]
            for row in normalized_result.summary["feature_importance"]
        }
        assert all(
            row["normalized"] is True for row in normalized_result.summary["feature_importance"]
        )
        assert normalized_result.summary["normalization"] == [
            {"column": "big", "mean": 0.0, "std": stats[0].std, "minimum": None, "maximum": None},
            {"column": "small", "mean": 0.0, "std": stats[1].std, "minimum": None, "maximum": None},
        ]
        assert normalized_result.summary["normalization_method"] == "zscore"

        # The bug: on raw data, "small" (the smaller-scale feature) needs a much
        # larger coefficient to matter as much as "big" does, so it ranks well
        # above "big" by |coefficient| alone despite both halves being equally
        # informative by construction.
        raw_ratio = raw_importance["small"] / raw_importance["big"]
        assert raw_ratio > 5.0, f"expected raw importance to be scale-biased, ratio={raw_ratio}"

        # The fix: after normalizing away the scale difference, this dataset's
        # own column-swap symmetry means the two features must land at
        # near-parity — the huge raw gap collapses.
        normalized_ratio = normalized_importance["small"] / normalized_importance["big"]
        assert 0.5 < normalized_ratio < 2.0, (
            f"expected near-parity after normalization, ratio={normalized_ratio}"
        )

        # The concrete, end-to-end proof: the same dataset+model produces a
        # measurably different Feature Importance ranking/ratio depending on
        # whether normalization was applied.
        assert raw_ratio != pytest.approx(normalized_ratio, rel=0.5)
