"""Random Forest — a real scikit-learn ensemble classifier.

The first non-linear model on the platform. Where `LogisticRegressionAdapter`
can only draw a single linear decision boundary through feature space, a
random forest is an ensemble of decision trees, each splitting on feature
*thresholds* and *interactions* a linear model structurally cannot represent —
so it is the natural instrument for a specific question the logistic-regression
baseline left open: when that baseline's own ROC-AUC is barely above 0.5, is
"no connector feature helps" a fact about the features, or a fact about a weak
linear model's inability to detect a weak signal? (See
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`.)

Trains on `TrainingDataset.train`, evaluates on `TrainingDataset.validation`
(recorded as this run's headline `metrics`) and, when present,
`TrainingDataset.test` — recording train/validation/test metrics separately
plus an overfitting flag (`app/training/interpretability.py`), a confusion
matrix (raw and per-class TP/FP/TN/FN/support), ROC/Precision-Recall curves
with AUC, feature importance (the forest's own mean-decrease-in-impurity
importances, `compute_impurity_feature_importance` — a more direct signal than
inferring value from a benchmark comparison), a capped prediction sample table
with per-row probability/confidence, model metadata, and the same set of
downloadable report artifacts (`app/training/artifact_files.py`) the two
baseline adapters produce. Requires a categorical (or otherwise discrete)
target column — `next_direction` (`"up"`/`"down"`/`"flat"`) is the built-in
target this pairs with naturally.

Default hyperparameters are deliberately modest — `n_estimators=200`,
`max_depth=8`, `min_samples_leaf=2`, `max_features="sqrt"` — not tuned. On
genuinely noisy financial data an unconstrained forest memorizes the training
rows; the point here is to detect whether *any* real signal exists that the
linear baseline missed, not to squeeze out maximum performance. All four are
overridable per job.
"""

import time
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
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
    compute_impurity_feature_importance,
    compute_overfitting_flag,
    compute_roc_pr_curves,
    to_float_list,
    to_float_matrix,
    to_int_matrix,
    to_label_list,
)
from app.training.model_metadata import collect_model_metadata
from app.training.normalization import normalization_stats_to_dicts
from app.training.registry import register
from app.training.serialization import default_serializer

#: Modest anti-overfit defaults — documented, not tuned (see module docstring).
DEFAULT_N_ESTIMATORS = 200
DEFAULT_MAX_DEPTH = 8
DEFAULT_MIN_SAMPLES_LEAF = 2
DEFAULT_MAX_FEATURES = "sqrt"
DEFAULT_RANDOM_SEED = 42


def _resolve_hyperparameters(hyperparameters: Mapping[str, Any]) -> dict[str, Any]:
    """The one place raw job hyperparameters become typed scikit-learn kwargs.

    `max_depth` accepts `None` (grow trees fully) as well as an int; every other
    value is coerced to its concrete type here so `initialize` and `train` can
    never disagree about what a job asked for.
    """
    raw_max_depth = hyperparameters.get("max_depth", DEFAULT_MAX_DEPTH)
    max_depth = None if raw_max_depth is None else int(raw_max_depth)
    return {
        "n_estimators": int(hyperparameters.get("n_estimators", DEFAULT_N_ESTIMATORS)),
        "max_depth": max_depth,
        "min_samples_leaf": int(hyperparameters.get("min_samples_leaf", DEFAULT_MIN_SAMPLES_LEAF)),
        "max_features": hyperparameters.get("max_features", DEFAULT_MAX_FEATURES),
        "random_seed": int(hyperparameters.get("random_seed", DEFAULT_RANDOM_SEED)),
    }


@register
class RandomForestAdapter(ModelAdapter):
    """A real scikit-learn `RandomForestClassifier` — the first non-linear model."""

    metadata = ModelAdapterMetadata(
        name="random_forest",
        label="Random Forest (Classification)",
        description=(
            "A scikit-learn RandomForestClassifier — an ensemble of decision trees, "
            "the first model on the platform able to capture non-linear feature "
            "interactions a linear baseline cannot. Pairs naturally with a categorical "
            "target such as next_direction."
        ),
        framework="scikit-learn",
        model_kind="classification",
        requires_real_data=True,
        hyperparameter_hints=(
            "n_estimators",
            "max_depth",
            "min_samples_leaf",
            "max_features",
            "random_seed",
        ),
    )

    def initialize(self, hyperparameters: Mapping[str, Any]) -> None:
        """Validates hyperparameter types only — scikit-learn validates values itself on fit."""
        _resolve_hyperparameters(hyperparameters)

    def train(self, dataset: TrainingDataset, hyperparameters: Mapping[str, Any]) -> TrainingResult:
        if dataset.train is None or dataset.validation is None:
            # `TrainingJobService` guarantees a real split for any `requires_real_data`
            # adapter before `train()` is ever called — reaching here means that
            # guarantee was violated, which is this adapter's own bug to report, not
            # a normal training failure.
            raise TrainingExecutionError(self.metadata.name, "no real training data was loaded")

        params = _resolve_hyperparameters(hyperparameters)

        # `SplitMatrix.X` is a plain `list[list[float]]` by design — this module
        # stays framework-free (`app/training/base.py`'s own docstring) — so each
        # split is converted to a real `numpy.ndarray` once, here, at the one seam
        # where a scikit-learn adapter actually needs one.
        train_x = np.asarray(dataset.train.X)
        validation_x = np.asarray(dataset.validation.X)

        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        try:
            model = RandomForestClassifier(
                n_estimators=params["n_estimators"],
                max_depth=params["max_depth"],
                min_samples_leaf=params["min_samples_leaf"],
                max_features=params["max_features"],
                random_state=params["random_seed"],
            )
            model.fit(train_x, dataset.train.y)
            # Every value scikit-learn hands back is converted through
            # `interpretability.py`'s typed helpers immediately (see that module's
            # `NumpyArrayLike` docstring for why: scikit-learn ships no type
            # information of its own).
            train_predictions = to_label_list(model.predict(train_x))
            train_probabilities = to_float_matrix(model.predict_proba(train_x))
            predictions = to_label_list(model.predict(validation_x))
            probabilities = to_float_matrix(model.predict_proba(validation_x))
        except Exception as exc:  # noqa: BLE001 - re-raised as a named domain error below
            raise TrainingExecutionError(
                self.metadata.name, f"{type(exc).__name__}: {exc}"
            ) from exc
        training_duration_seconds = time.perf_counter() - wall_started
        cpu_time_seconds = time.process_time() - cpu_started

        classes = to_label_list(model.classes_)
        # `EvaluationEngine.evaluate` (`app/evaluation/`) is the one place these
        # numbers are computed — the exact same engine (and metrics) the two
        # baseline adapters use, never reimplemented here.
        metrics = evaluation_engine.evaluate(
            self.metadata.model_kind, dataset.validation.y, predictions, probabilities
        ).metrics
        train_metrics = evaluation_engine.evaluate(
            self.metadata.model_kind, dataset.train.y, train_predictions, train_probabilities
        ).metrics
        matrix = to_int_matrix(confusion_matrix(dataset.validation.y, predictions, labels=classes))
        confusion_details = compute_confusion_details(dataset.validation.y, predictions, classes)
        roc_pr = compute_roc_pr_curves(dataset.validation.y, probabilities, classes)
        feature_importance = compute_impurity_feature_importance(
            dataset.feature_columns,
            to_float_list(model.feature_importances_),
            normalized=dataset.normalization is not None,
        )
        prediction_samples = build_prediction_samples(
            actual=dataset.validation.y,
            predicted=predictions,
            probabilities=probabilities,
            classes=classes,
        )
        artifact_uri = default_serializer.save(model, self.metadata.name)

        test_metrics: dict[str, float] = {}
        held_out_metrics = metrics
        if dataset.test is not None and len(dataset.test.y) > 0:
            test_x = np.asarray(dataset.test.X)
            test_predictions = to_label_list(model.predict(test_x))
            test_probabilities = to_float_matrix(model.predict_proba(test_x))
            test_metrics = evaluation_engine.evaluate(
                self.metadata.model_kind,
                dataset.test.y,
                test_predictions,
                test_probabilities,
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
            "confusion_matrix": matrix,
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
                "n_estimators": params["n_estimators"],
                "max_depth": params["max_depth"],
                "min_samples_leaf": params["min_samples_leaf"],
                "max_features": params["max_features"],
                "random_seed": params["random_seed"],
            },
            "normalization": normalization_stats_to_dicts(dataset.normalization),
            "normalization_method": dataset.normalization_method,
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
                self.metadata.name, matrix, [str(c) for c in classes]
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
