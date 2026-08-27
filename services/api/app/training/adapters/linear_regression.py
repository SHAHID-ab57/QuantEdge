"""Linear Regression — a real scikit-learn baseline regressor.

Every advanced regression model this platform eventually adds must be able to
outperform this. Trains on `TrainingDataset.train`, evaluates on
`TrainingDataset.validation` (this run's headline `metrics`) and, when present,
`TrainingDataset.test` — recording train/validation/test metrics separately plus an
overfitting flag (`app/training/interpretability.py`), feature importance
(coefficients ranked by absolute magnitude — the same helper `LogisticRegressionAdapter`
uses, given a single-row coefficient vector instead of one row per class), a capped
prediction sample table, model metadata (library versions, timing, memory, dataset
shape), and a set of downloadable report artifacts (`app/training/artifact_files.py`).
There is no confusion matrix or ROC/PR curve for a regressor — those are
classification-only concepts, so only `metrics.json`/`training_report.json`/
`feature_importance.csv` are produced here. Requires a numeric target column —
`next_close`/`next_return` are the built-in targets this pairs with naturally (see
`app/training/dataset_loader.py`'s `IncompatibleTargetDtypeError`, raised if a
categorical target is given instead).
"""

import math
import time
from collections.abc import Mapping, Sequence
from typing import Any

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from app.training.artifact_files import (
    write_feature_importance_csv,
    write_metrics_json,
    write_training_report_json,
)
from app.training.base import ModelAdapter, ModelAdapterMetadata, TrainingDataset, TrainingResult
from app.training.errors import TrainingExecutionError
from app.training.interpretability import (
    build_prediction_samples,
    compute_feature_importance,
    compute_overfitting_flag,
)
from app.training.model_metadata import collect_model_metadata
from app.training.registry import register
from app.training.serialization import default_serializer


def _regression_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> dict[str, float]:
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "mse": mse,
        "rmse": math.sqrt(mse),
        "r2": float(r2_score(y_true, y_pred)),
    }


@register
class LinearRegressionAdapter(ModelAdapter):
    """A real scikit-learn `LinearRegression` baseline regressor."""

    metadata = ModelAdapterMetadata(
        name="linear_regression",
        label="Linear Regression (Baseline)",
        description=(
            "A scikit-learn LinearRegression baseline regressor. Every advanced "
            "regression model must outperform it. Pairs naturally with a numeric "
            "target such as next_close or next_return."
        ),
        framework="scikit-learn",
        model_kind="regression",
        requires_real_data=True,
        hyperparameter_hints=("fit_intercept",),
    )

    def initialize(self, hyperparameters: Mapping[str, Any]) -> None:
        """Validates hyperparameter types only — scikit-learn validates values itself on fit."""
        bool(hyperparameters.get("fit_intercept", True))

    def train(self, dataset: TrainingDataset, hyperparameters: Mapping[str, Any]) -> TrainingResult:
        if dataset.train is None or dataset.validation is None:
            # `TrainingJobService` guarantees a real split for any `requires_real_data`
            # adapter before `train()` is ever called — reaching here means that
            # guarantee was violated, which is this adapter's own bug to report, not
            # a normal training failure.
            raise TrainingExecutionError(self.metadata.name, "no real training data was loaded")

        fit_intercept = bool(hyperparameters.get("fit_intercept", True))

        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        try:
            model = LinearRegression(fit_intercept=fit_intercept)
            model.fit(dataset.train.X, dataset.train.y)
            train_predictions = model.predict(dataset.train.X)
            predictions = model.predict(dataset.validation.X)
        except Exception as exc:  # noqa: BLE001 - re-raised as a named domain error below
            raise TrainingExecutionError(
                self.metadata.name, f"{type(exc).__name__}: {exc}"
            ) from exc
        training_duration_seconds = time.perf_counter() - wall_started
        cpu_time_seconds = time.process_time() - cpu_started

        metrics = _regression_metrics(dataset.validation.y, predictions)
        train_metrics = _regression_metrics(dataset.train.y, train_predictions)
        # `model.coef_` is a 1-D ndarray for single-output regression; wrapped in a
        # one-row list so `compute_feature_importance` sees the same "one row per
        # class" shape `LogisticRegressionAdapter` gives it. sklearn's stubs type
        # `coef_` as incompatible with `Sequence[float]` despite behaving as one at
        # runtime (a known stub-completeness gap, same as `zero_division` elsewhere).
        feature_importance = compute_feature_importance(
            dataset.feature_columns,
            [model.coef_.tolist()],  # type: ignore[reportAttributeAccessIssue]
        )
        prediction_samples = build_prediction_samples(
            actual=dataset.validation.y, predicted=predictions.tolist()
        )
        artifact_uri = default_serializer.save(model, self.metadata.name)

        test_metrics: dict[str, float] = {}
        held_out_metrics = metrics
        if dataset.test is not None and len(dataset.test.y) > 0:
            test_predictions = model.predict(dataset.test.X)
            test_metrics = _regression_metrics(dataset.test.y, test_predictions)
            held_out_metrics = test_metrics
        overfitting = compute_overfitting_flag(
            train_metrics["r2"], held_out_metrics["r2"], higher_is_better=True
        )
        model_metadata = collect_model_metadata(
            feature_count=len(dataset.feature_columns),
            sample_count=(
                len(dataset.train.y)
                + len(dataset.validation.y)
                + (len(dataset.test.y) if dataset.test is not None else 0)
            ),
            training_duration_seconds=training_duration_seconds,
            cpu_time_seconds=cpu_time_seconds,
        )

        report = {
            "target_column": dataset.target_column,
            "feature_columns": list(dataset.feature_columns),
            "coefficients": model.coef_.tolist(),
            "intercept": float(model.intercept_),
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
            "overfitting": overfitting,
            "feature_importance": feature_importance,
            "prediction_samples": prediction_samples,
            "model_metadata": model_metadata,
            "n_train": len(dataset.train.y),
            "n_validation": len(dataset.validation.y),
            "n_test": len(dataset.test.y) if dataset.test is not None else 0,
            "hyperparameters": {"fit_intercept": fit_intercept},
        }
        artifacts = {
            "metrics_json": write_metrics_json(
                self.metadata.name,
                {"metrics": metrics, "train_metrics": train_metrics, "test_metrics": test_metrics},
            ),
            "training_report_json": write_training_report_json(self.metadata.name, report),
            "feature_importance_csv": write_feature_importance_csv(
                self.metadata.name, feature_importance
            ),
        }
        report["artifacts"] = artifacts

        return TrainingResult(metrics=metrics, artifact_uri=artifact_uri, summary=report)

    def predict(self, artifact_uri: str, rows: Sequence[Sequence[float]]) -> list[Any]:
        model = default_serializer.load(artifact_uri)
        return model.predict(list(rows)).tolist()
