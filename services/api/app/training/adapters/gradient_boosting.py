"""Gradient Boosting — a real scikit-learn boosted-tree classifier.

Where `RandomForestAdapter` bags many deep-ish trees and averages their
votes, gradient boosting fits a sequence of *shallow* trees, each one
correcting the previous ensemble's residual error — a genuinely different
inductive bias (additive, sequential, error-correcting) from bagging, not
just "more trees." On tabular data of this shape (few dozen numeric
columns, tens of thousands of rows) it is often the strongest of the two,
which makes it the natural next instrument after `RandomForestAdapter`
already failed to find signal `LogisticRegressionAdapter` missed — see
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`.

Uses `sklearn.ensemble.HistGradientBoostingClassifier` — scikit-learn's
histogram-binned boosting implementation (the same family XGBoost/LightGBM
popularized), already available from the pinned `scikit-learn` dependency,
no new package required. Its own built-in early stopping is explicitly
disabled (`early_stopping=False`): left on, it would carve a *random*
validation subset out of whatever is passed to `.fit()` internally,
which would both violate this platform's chronological-only splitting
policy (`app/ml_datasets/split.py`'s `ChronologicalSplitter` — "never
shuffled and never interleaved") and quietly compete with this framework's
own `TrainingDataset.validation`, which is the one held-out split every
adapter is actually evaluated against. Training always runs the full
`max_iter` boosting rounds against `dataset.train` alone.

Has no native feature-importance/coefficient attribute (that's a
bagged-tree-ensemble convention `RandomForestClassifier` follows and a
linear-model convention `LogisticRegressionAdapter`/`LinearRegressionAdapter`
follow — boosting has neither), so feature attribution uses **permutation
importance** instead (`app/training/interpretability.py`'s
`compute_permutation_importance`), computed against the held-out
validation split — see that function's own docstring for why train would
be the wrong choice, and why a negative reported importance is left
un-clamped rather than treated as an error.

Trains on `TrainingDataset.train`, evaluates on `TrainingDataset.validation`
(recorded as this run's headline `metrics`) and, when present,
`TrainingDataset.test` — the same train/validation/test metrics, overfitting
flag, confusion matrix, ROC/Precision-Recall curves, capped prediction
sample table, model metadata, and downloadable report artifacts the other
two real adapters produce. Requires a categorical (or otherwise discrete)
target column — `next_direction` (`"up"`/`"down"`/`"flat"`) is the built-in
target this pairs with naturally.

Default hyperparameters are reasonable, documented defaults — not
exhaustively tuned, the same posture `RandomForestAdapter`'s own module
docstring states: `max_iter=200` (boosting rounds), `max_depth=6` (shallow
trees, boosting's own anti-overfit lever — unlike a bagged forest, an
unconstrained sequence of deep boosted trees overfits fast),
`learning_rate=0.1` and `min_samples_leaf=20` (scikit-learn's own
defaults). All five are overridable per job.
"""

import time
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
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
    compute_overfitting_flag,
    compute_permutation_importance,
    compute_roc_pr_curves,
    to_float_matrix,
    to_int_matrix,
    to_label_list,
)
from app.training.model_metadata import collect_model_metadata
from app.training.normalization import normalization_stats_to_dicts
from app.training.registry import register
from app.training.serialization import default_serializer

#: Reasonable, documented defaults — not tuned (see module docstring).
DEFAULT_MAX_ITER = 200
DEFAULT_MAX_DEPTH = 6
DEFAULT_LEARNING_RATE = 0.1
DEFAULT_MIN_SAMPLES_LEAF = 20
DEFAULT_RANDOM_SEED = 42

#: Permutation importance settings — fixed, documented, not per-job
#: hyperparameters (they control how attribution is *measured*, not how
#: the model itself is fit).
PERMUTATION_SCORING = "accuracy"
PERMUTATION_N_REPEATS = 10


def _resolve_hyperparameters(hyperparameters: Mapping[str, Any]) -> dict[str, Any]:
    """The one place raw job hyperparameters become typed scikit-learn kwargs.

    `max_depth` accepts `None` (sklearn's own "unlimited" sentinel) as well
    as an int, mirroring `RandomForestAdapter._resolve_hyperparameters`.
    """
    raw_max_depth = hyperparameters.get("max_depth", DEFAULT_MAX_DEPTH)
    max_depth = None if raw_max_depth is None else int(raw_max_depth)
    return {
        "max_iter": int(hyperparameters.get("max_iter", DEFAULT_MAX_ITER)),
        "max_depth": max_depth,
        "learning_rate": float(hyperparameters.get("learning_rate", DEFAULT_LEARNING_RATE)),
        "min_samples_leaf": int(hyperparameters.get("min_samples_leaf", DEFAULT_MIN_SAMPLES_LEAF)),
        "random_seed": int(hyperparameters.get("random_seed", DEFAULT_RANDOM_SEED)),
    }


@register
class GradientBoostingAdapter(ModelAdapter):
    """A real scikit-learn `HistGradientBoostingClassifier` — sequential, error-correcting."""

    metadata = ModelAdapterMetadata(
        name="gradient_boosting",
        label="Gradient Boosting (Classification)",
        description=(
            "A scikit-learn HistGradientBoostingClassifier — a sequential, "
            "error-correcting ensemble of shallow trees, distinct in kind from "
            "Random Forest's bagging. Pairs naturally with a categorical target "
            "such as next_direction."
        ),
        framework="scikit-learn",
        model_kind="classification",
        requires_real_data=True,
        hyperparameter_hints=(
            "max_iter",
            "max_depth",
            "learning_rate",
            "min_samples_leaf",
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
            model = HistGradientBoostingClassifier(
                max_iter=params["max_iter"],
                max_depth=params["max_depth"],
                learning_rate=params["learning_rate"],
                min_samples_leaf=params["min_samples_leaf"],
                random_state=params["random_seed"],
                # See module docstring: sklearn's own built-in early stopping
                # would carve a *random* validation subset out of `train_x`
                # internally, violating this platform's chronological-only
                # splitting policy and competing with `dataset.validation`,
                # which is the one held-out split this adapter is actually
                # evaluated against. Always run the full `max_iter` rounds.
                # The bundled stub only types this parameter as `str`; the
                # real runtime signature accepts `bool | str` (default
                # `"auto"`) — a stub gap, not a real type error.
                early_stopping=False,  # type: ignore[arg-type]
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
        # numbers are computed — the exact same engine (and metrics) the other
        # two real adapters use, never reimplemented here.
        metrics = evaluation_engine.evaluate(
            self.metadata.model_kind, dataset.validation.y, predictions, probabilities
        ).metrics
        train_metrics = evaluation_engine.evaluate(
            self.metadata.model_kind, dataset.train.y, train_predictions, train_probabilities
        ).metrics
        matrix = to_int_matrix(confusion_matrix(dataset.validation.y, predictions, labels=classes))
        confusion_details = compute_confusion_details(dataset.validation.y, predictions, classes)
        roc_pr = compute_roc_pr_curves(dataset.validation.y, probabilities, classes)
        # Permutation importance, not impurity/coefficient importance — this
        # model has neither. Measured against the held-out validation split,
        # never train (see `compute_permutation_importance`'s own docstring).
        feature_importance = compute_permutation_importance(
            dataset.feature_columns,
            model,
            validation_x,
            dataset.validation.y,
            scoring=PERMUTATION_SCORING,
            n_repeats=PERMUTATION_N_REPEATS,
            random_state=params["random_seed"],
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
            "feature_importance_method": "permutation",
            "prediction_samples": prediction_samples,
            "model_metadata": model_metadata,
            "n_train": len(dataset.train.y),
            "n_validation": len(dataset.validation.y),
            "n_test": len(dataset.test.y) if dataset.test is not None else 0,
            "hyperparameters": {
                "max_iter": params["max_iter"],
                "max_depth": params["max_depth"],
                "learning_rate": params["learning_rate"],
                "min_samples_leaf": params["min_samples_leaf"],
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
