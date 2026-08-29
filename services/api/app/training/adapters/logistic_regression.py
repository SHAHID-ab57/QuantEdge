"""Logistic Regression — a real scikit-learn baseline classifier.

Every advanced classification model this platform eventually adds must be able to
outperform this. Trains on `TrainingDataset.train`, evaluates on
`TrainingDataset.validation` (recorded as this run's headline `metrics`) and, when
present, `TrainingDataset.test` — recording train/validation/test metrics separately
plus an overfitting flag (`app/training/interpretability.py`), a confusion matrix (raw
and per-class TP/FP/TN/FN/support), ROC/Precision-Recall curves with AUC, feature
importance (coefficients ranked by absolute magnitude), a capped prediction sample
table with per-row probability/confidence, model metadata (library versions,
timing, memory, dataset shape), and a set of downloadable report artifacts
(`app/training/artifact_files.py`) — all additive to the confusion-matrix-plus-metrics
contract this adapter has always exposed. Requires a categorical (or otherwise
discrete) target column — `next_direction` (`"up"`/`"down"`/`"flat"`) is the built-in
target this pairs with naturally.
"""

import time
from collections.abc import Mapping, Sequence
from typing import Any

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix

from app.evaluation.engine import default_engine as evaluation_engine
from app.training.artifact_files import (
    write_confusion_matrix_png,
    write_feature_importance_csv,
    write_metrics_json,
    write_precision_recall_curve_png,
    write_roc_curve_png,
    write_training_report_json,
)
from app.training.base import ModelAdapter, ModelAdapterMetadata, TrainingDataset, TrainingResult
from app.training.errors import TrainingExecutionError
from app.training.interpretability import (
    build_prediction_samples,
    compute_confusion_details,
    compute_feature_importance,
    compute_overfitting_flag,
    compute_roc_pr_curves,
)
from app.training.model_metadata import collect_model_metadata
from app.training.registry import register
from app.training.serialization import default_serializer


@register
class LogisticRegressionAdapter(ModelAdapter):
    """A real scikit-learn `LogisticRegression` baseline classifier."""

    metadata = ModelAdapterMetadata(
        name="logistic_regression",
        label="Logistic Regression (Baseline)",
        description=(
            "A scikit-learn LogisticRegression baseline classifier. Every advanced "
            "classification model must outperform it. Pairs naturally with a categorical "
            "target such as next_direction."
        ),
        framework="scikit-learn",
        model_kind="classification",
        requires_real_data=True,
        hyperparameter_hints=("max_iter", "C", "random_seed"),
    )

    def initialize(self, hyperparameters: Mapping[str, Any]) -> None:
        """Validates hyperparameter types only — scikit-learn validates values itself on fit."""
        int(hyperparameters.get("max_iter", 200))
        float(hyperparameters.get("C", 1.0))
        int(hyperparameters.get("random_seed", 42))

    def train(self, dataset: TrainingDataset, hyperparameters: Mapping[str, Any]) -> TrainingResult:
        if dataset.train is None or dataset.validation is None:
            # `TrainingJobService` guarantees a real split for any `requires_real_data`
            # adapter before `train()` is ever called — reaching here means that
            # guarantee was violated, which is this adapter's own bug to report, not
            # a normal training failure.
            raise TrainingExecutionError(self.metadata.name, "no real training data was loaded")

        max_iter = int(hyperparameters.get("max_iter", 200))
        regularization = float(hyperparameters.get("C", 1.0))
        random_seed = int(hyperparameters.get("random_seed", 42))

        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        try:
            model = LogisticRegression(
                max_iter=max_iter, C=regularization, random_state=random_seed
            )
            model.fit(dataset.train.X, dataset.train.y)
            train_predictions = model.predict(dataset.train.X)
            train_probabilities = model.predict_proba(dataset.train.X)
            predictions = model.predict(dataset.validation.X)
            probabilities = model.predict_proba(dataset.validation.X)
        except Exception as exc:  # noqa: BLE001 - re-raised as a named domain error below
            raise TrainingExecutionError(
                self.metadata.name, f"{type(exc).__name__}: {exc}"
            ) from exc
        training_duration_seconds = time.perf_counter() - wall_started
        cpu_time_seconds = time.process_time() - cpu_started

        classes = model.classes_.tolist()
        # `EvaluationEngine.evaluate` (`app/evaluation/`) is the one place these
        # numbers are actually computed — every metric it runs (including ROC-AUC,
        # new here) is a registered `Metric`, so a future model adapter reuses the
        # exact same engine rather than reimplementing this math a third time.
        metrics = evaluation_engine.evaluate(
            self.metadata.model_kind, dataset.validation.y, predictions, probabilities.tolist()
        ).metrics
        train_metrics = evaluation_engine.evaluate(
            self.metadata.model_kind,
            dataset.train.y,
            train_predictions,
            train_probabilities.tolist(),
        ).metrics
        matrix = confusion_matrix(dataset.validation.y, predictions, labels=classes)
        confusion_details = compute_confusion_details(dataset.validation.y, predictions, classes)
        roc_pr = compute_roc_pr_curves(dataset.validation.y, probabilities.tolist(), classes)
        feature_importance = compute_feature_importance(dataset.feature_columns, model.coef_)
        prediction_samples = build_prediction_samples(
            actual=dataset.validation.y,
            # sklearn's stubs infer an incomplete return type for `predict()` here (a
            # known stub-completeness gap, same as `zero_division` above) — the
            # runtime value is always an ndarray with a real `.tolist()`.
            predicted=predictions.tolist(),  # type: ignore[reportAttributeAccessIssue]
            probabilities=probabilities.tolist(),
            classes=classes,
        )
        artifact_uri = default_serializer.save(model, self.metadata.name)

        test_metrics: dict[str, float] = {}
        held_out_metrics = metrics
        if dataset.test is not None and len(dataset.test.y) > 0:
            test_predictions = model.predict(dataset.test.X)
            test_probabilities = model.predict_proba(dataset.test.X)
            test_metrics = evaluation_engine.evaluate(
                self.metadata.model_kind,
                dataset.test.y,
                test_predictions,
                test_probabilities.tolist(),
            ).metrics
            held_out_metrics = test_metrics
        overfitting = compute_overfitting_flag(
            train_metrics["accuracy"], held_out_metrics["accuracy"], higher_is_better=True
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
            "classes": classes,
            "confusion_matrix": matrix.tolist(),
            "confusion_matrix_details": confusion_details,
            "roc_pr_curves": roc_pr,
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
            "overfitting": overfitting,
            "feature_importance": feature_importance,
            "prediction_samples": prediction_samples,
            "model_metadata": model_metadata,
            "n_train": len(dataset.train.y),
            "n_validation": len(dataset.validation.y),
            "n_test": len(dataset.test.y) if dataset.test is not None else 0,
            "hyperparameters": {
                "max_iter": max_iter,
                "C": regularization,
                "random_seed": random_seed,
            },
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
            "confusion_matrix_png": write_confusion_matrix_png(
                self.metadata.name, matrix.tolist(), [str(c) for c in classes]
            ),
            "roc_curve_png": write_roc_curve_png(
                self.metadata.name, roc_pr["curves"], roc_pr["auc"]
            ),
            "precision_recall_curve_png": write_precision_recall_curve_png(
                self.metadata.name, roc_pr["curves"]
            ),
        }
        report["artifacts"] = artifacts

        return TrainingResult(metrics=metrics, artifact_uri=artifact_uri, summary=report)

    def predict(self, artifact_uri: str, rows: Sequence[Sequence[float]]) -> list[Any]:
        model = default_serializer.load(artifact_uri)
        return model.predict(list(rows)).tolist()

    def predict_proba(
        self, artifact_uri: str, rows: Sequence[Sequence[float]]
    ) -> list[list[float]] | None:
        model = default_serializer.load(artifact_uri)
        return model.predict_proba(list(rows)).tolist()
