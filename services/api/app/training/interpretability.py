"""Model interpretability and evaluation helpers shared by the real scikit-learn adapters.

Adapter-level support code, not a pipeline/registry/serializer change:
`logistic_regression.py` and `linear_regression.py` import this module directly and put
its output straight into `TrainingResult.summary` — nothing here touches
`app/training/pipeline.py`, `registry.py`, or `serialization.py`, and nothing here is
itself a `ModelAdapter`.
"""

from collections.abc import Sequence
from typing import Any

#: Prediction-confidence thresholds — a fixed, documented heuristic (not derived from
#: any dataset), matching the same "explicitly-labeled heuristic" spirit the Dataset
#: Validation page's client-side Quality Score already uses for its own thresholds.
HIGH_CONFIDENCE_THRESHOLD = 0.7
MEDIUM_CONFIDENCE_THRESHOLD = 0.5

#: How far a train metric may exceed its held-out counterpart before a run is flagged
#: as possibly overfitting — a fixed, documented heuristic, not a statistical test.
DEFAULT_OVERFITTING_THRESHOLD = 0.15

#: How many rows of the Prediction Inspection / Prediction Confidence sample table to
#: keep — enough to be useful, small enough that `result_summary` (a single JSON
#: column) never grows unbounded on a large validation split.
DEFAULT_PREDICTION_SAMPLE_CAP = 25


def confidence_level(probability: float) -> str:
    """Bucket a predicted-class probability into "high"/"medium"/"low"."""
    if probability >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if probability >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def compute_feature_importance(
    feature_columns: Sequence[str],
    coefficients: Sequence[Sequence[float]],
    *,
    normalized: bool = False,
) -> list[dict[str, Any]]:
    """Rank features by mean absolute coefficient magnitude.

    `coefficients` is one row per class for a multi-class classifier
    (`LogisticRegression.coef_`) or a single-row wrapper around a flat vector for a
    regressor (`[LinearRegression.coef_]`). For more than one class, the reported
    `coefficient`/`sign` average across classes — a feature that pushes strongly
    toward one class and against another nets out near zero, which is an accurate
    (if conservative) summary for a single ranked table, not a per-class breakdown.

    `normalized` records (per row, never changing the ranking math itself) whether
    `coefficients` were fit on already-normalized features
    (`app/training/normalization.py`) — a caller-supplied fact about the input,
    not something this function can detect on its own. This is the one thing that
    actually makes a cross-feature magnitude comparison meaningful: comparing raw
    coefficients across features of different natural scale (`close` vs.
    `candle_body`) is scale-biased regardless of how they're ranked here, so every
    row is tagged so a report reader (and `FeatureImportancePanel`'s own label)
    can tell a scale-comparable run from a scale-biased one at a glance.
    """
    n_features = len(feature_columns)
    n_rows = len(coefficients) or 1
    sums_abs = [0.0] * n_features
    sums_signed = [0.0] * n_features
    for row in coefficients:
        for index, value in enumerate(row):
            sums_abs[index] += abs(float(value))
            sums_signed[index] += float(value)

    rows = []
    for index, name in enumerate(feature_columns):
        abs_importance = sums_abs[index] / n_rows
        mean_coefficient = sums_signed[index] / n_rows
        if mean_coefficient > 0:
            sign = "positive"
        elif mean_coefficient < 0:
            sign = "negative"
        else:
            sign = "neutral"
        rows.append(
            {
                "feature": name,
                "coefficient": mean_coefficient,
                "abs_importance": abs_importance,
                "sign": sign,
                "normalized": normalized,
            }
        )
    rows.sort(key=lambda row: row["abs_importance"], reverse=True)
    return rows


def compute_confusion_details(
    y_true: Sequence[Any], y_pred: Sequence[Any], labels: Sequence[Any]
) -> list[dict[str, Any]]:
    """Per-class True/False Positive/Negative counts and support, one-vs-rest."""
    from sklearn.metrics import multilabel_confusion_matrix

    matrices = multilabel_confusion_matrix(y_true, y_pred, labels=list(labels))
    details = []
    for label, matrix in zip(labels, matrices, strict=True):
        true_negative, false_positive, false_negative, true_positive = matrix.ravel().tolist()
        details.append(
            {
                "class": label,
                "true_positive": int(true_positive),
                "false_positive": int(false_positive),
                "true_negative": int(true_negative),
                "false_negative": int(false_negative),
                "support": int(true_positive + false_negative),
            }
        )
    return details


def compute_roc_pr_curves(
    y_true: Sequence[Any], y_proba: Sequence[Sequence[float]], labels: Sequence[Any]
) -> dict[str, Any]:
    """One-vs-rest ROC and Precision-Recall curves, plus per-class AUC/average precision.

    Every classifier this framework baselines against (multi-class `next_direction`
    included) is scored the same way: each class in turn is treated as "positive",
    every other class as "negative" — the standard one-vs-rest reduction for a
    multi-class ROC/PR curve, and exact for the binary case.
    """
    from sklearn.metrics import auc, average_precision_score, precision_recall_curve, roc_curve
    from sklearn.preprocessing import label_binarize

    labels = list(labels)
    binarized = label_binarize(y_true, classes=labels)
    if len(labels) == 2:
        # `label_binarize` collapses a 2-class problem to one column; rebuild the
        # second (negative-class) column so both classes get a curve, symmetric with
        # the 3+-class case.
        binarized = [[1 - row[0], row[0]] for row in binarized]

    curves: dict[Any, dict[str, Any]] = {}
    auc_scores: dict[Any, float] = {}
    average_precision: dict[Any, float] = {}
    for index, label in enumerate(labels):
        column_true = [row[index] for row in binarized]
        column_score = [row[index] for row in y_proba]
        false_positive_rate, true_positive_rate, _ = roc_curve(column_true, column_score)
        precision, recall, _ = precision_recall_curve(column_true, column_score)
        curves[label] = {
            "roc": {"fpr": false_positive_rate.tolist(), "tpr": true_positive_rate.tolist()},
            "pr": {"precision": precision.tolist(), "recall": recall.tolist()},
        }
        auc_scores[label] = float(auc(false_positive_rate, true_positive_rate))
        average_precision[label] = float(average_precision_score(column_true, column_score))

    return {
        "curves": curves,
        "auc": auc_scores,
        "average_precision": average_precision,
        "macro_auc": (sum(auc_scores.values()) / len(auc_scores)) if auc_scores else None,
    }


def build_prediction_samples(
    *,
    actual: Sequence[Any],
    predicted: Sequence[Any],
    probabilities: Sequence[Sequence[float]] | None = None,
    classes: Sequence[Any] | None = None,
    cap: int = DEFAULT_PREDICTION_SAMPLE_CAP,
) -> list[dict[str, Any]]:
    """A capped Actual/Predicted/Probability/Confidence/Correct sample table.

    For a classifier (`probabilities`/`classes` both given), each row's probability is
    the predicted class's own probability and `correct` compares actual to predicted
    directly. For a regressor (both `None`), `probability`/`confidence_level`/`correct`
    are all `None` — there is no class to be confident about or "correct" against,
    only a continuous value; the frontend renders those columns as "—" rather than
    fabricating a meaning for them.
    """
    is_classification = probabilities is not None and classes is not None
    samples = []
    for index in range(min(len(actual), len(predicted), cap)):
        probability = None
        confidence = None
        if is_classification and probabilities is not None:
            row_probabilities = probabilities[index]
            best = max(range(len(row_probabilities)), key=lambda j: row_probabilities[j])
            probability = float(row_probabilities[best])
            confidence = confidence_level(probability)
        samples.append(
            {
                "actual": actual[index],
                "predicted": predicted[index],
                "probability": probability,
                "confidence_level": confidence,
                "correct": (actual[index] == predicted[index]) if is_classification else None,
            }
        )
    return samples


def compute_overfitting_flag(
    train_value: float,
    held_out_value: float,
    *,
    higher_is_better: bool,
    threshold: float = DEFAULT_OVERFITTING_THRESHOLD,
) -> dict[str, Any]:
    """Flag "Train >> held-out" — a fixed-threshold heuristic, not a statistical test.

    `higher_is_better` picks the direction: accuracy/F1/R² are better when higher, so
    a large positive `train - held_out` gap is suspicious; MAE/MSE/RMSE are better when
    lower, so the same suspicious direction is `held_out - train` (the model does much
    worse once it can't just recall the training rows).
    """
    gap = (train_value - held_out_value) if higher_is_better else (held_out_value - train_value)
    flagged = gap > threshold
    return {
        "flagged": flagged,
        "gap": gap,
        "threshold": threshold,
        "message": (
            f"Train metric exceeds the held-out metric by {gap:.4f} (> {threshold}) — "
            "possible overfitting."
            if flagged
            else "No significant train / held-out gap detected."
        ),
    }
