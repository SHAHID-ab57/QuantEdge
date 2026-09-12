"""Model interpretability and evaluation helpers shared by the real scikit-learn adapters.

Adapter-level support code, not a pipeline/registry/serializer change:
`logistic_regression.py` and `linear_regression.py` import this module directly and put
its output straight into `TrainingResult.summary` — nothing here touches
`app/training/pipeline.py`, `registry.py`, or `serialization.py`, and nothing here is
itself a `ModelAdapter`.
"""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class NumpyArrayLike(Protocol):
    """Structural contract for whatever scikit-learn/numpy actually hands back at
    runtime — a `numpy.ndarray` — for the one method every conversion helper below
    needs from it.

    scikit-learn ships no type information of its own (no `py.typed` marker), so
    a value that comes back from a model attribute (`model.coef_`,
    `model.classes_`) or a `sklearn.metrics`/`sklearn.preprocessing` function
    (`confusion_matrix`, `roc_curve`, `precision_recall_curve`,
    `multilabel_confusion_matrix`, `label_binarize`) is only ever as precisely
    typed as whichever stub set (if any) happens to be installed — and even with
    one installed, tracing an untyped call graph can still produce an inferred
    type describing more runtime shapes than the call actually takes (e.g. a
    `tuple` branch merged in from a generic base-class method this platform's
    two real model adapters never actually reach). Every `to_*` helper below
    therefore accepts plain `object` and narrows to this Protocol itself, via
    `_ensure_array` — `@runtime_checkable` makes that a real structural check at
    runtime, not just an assumption — so each one is correct regardless of which
    of those situations applies at its own call site.
    """

    # numpy's own stubs type `tolist()` `-> Any` too — the nested shape genuinely
    # can't be expressed statically, so `object` is the honest upper bound here;
    # `_ensure_array` narrows it explicitly before it's ever called.
    def tolist(self) -> object: ...


def _ensure_array(value: object, *, what: str = "an array-like with .tolist()") -> NumpyArrayLike:
    """The one narrowing check every conversion helper below shares: confirm
    `value` actually has a real `.tolist()` before calling it, rather than
    trusting whatever static type it happened to arrive with. See
    `NumpyArrayLike`'s own docstring for why this can't just be assumed from the
    parameter's declared type."""
    if isinstance(value, NumpyArrayLike):
        return value
    raise TypeError(f"expected {what}, got {type(value).__name__}")


def _as_list(raw: object, *, what: str) -> list[object]:
    """The common second step every conversion helper needs: confirm `tolist()`
    actually produced a `list` before indexing/iterating it — raising with a clear
    message rather than trusting an unknown-shaped value silently."""
    if not isinstance(raw, list):
        raise TypeError(f"expected {what}, got {type(raw).__name__}")
    return raw


def _as_float(item: object) -> float:
    """Narrow one already-unpacked array element to `float`, the same
    `isinstance(value, int | float)` discipline `app/training/normalization.py`'s
    own numeric-column narrowing already uses — `object` has no `__float__` of its
    own, so `float(item)` is only ever valid once `item` is actually narrowed."""
    if isinstance(item, int | float):
        return float(item)
    raise TypeError(f"expected a numeric array element, got {type(item).__name__}")


def _as_int(item: object) -> int:
    """`_as_float`'s integer counterpart — a count (a confusion-matrix cell, a
    true/false positive/negative) is always whole, but still arrives as `object`."""
    if isinstance(item, int | float):
        return int(item)
    raise TypeError(f"expected a numeric array element, got {type(item).__name__}")


def to_float_list(value: object) -> list[float]:
    """One 1-D numpy array's values as a real, validated `list[float]` — e.g. a
    `roc_curve`/`precision_recall_curve` output column."""
    raw = _ensure_array(value, what="a 1-D array-like").tolist()
    return [_as_float(item) for item in _as_list(raw, what="a 1-D array-like")]


def to_int_list(value: object) -> list[int]:
    """One 1-D numpy array's values as a real, validated `list[int]` — e.g. one
    `multilabel_confusion_matrix` entry's own `.ravel()`."""
    raw = _ensure_array(value, what="a 1-D array-like").tolist()
    return [_as_int(item) for item in _as_list(raw, what="a 1-D array-like")]


def to_float_matrix(value: object) -> list[list[float]]:
    """One 2-D numpy array's values as a real, validated `list[list[float]]` — e.g.
    `model.predict_proba(...)` or a (never-sparse-in-practice) `label_binarize`
    result."""
    rows = _as_list(_ensure_array(value, what="a 2-D array-like").tolist(), what="a 2-D array-like")
    return [
        [_as_float(item) for item in _as_list(row, what="a 2-D array-like row")] for row in rows
    ]


def to_int_matrix(value: object) -> list[list[int]]:
    """One 2-D numpy integer array's values as a real, validated
    `list[list[int]]` — e.g. `sklearn.metrics.confusion_matrix`'s output."""
    rows = _as_list(_ensure_array(value, what="a 2-D array-like").tolist(), what="a 2-D array-like")
    return [[_as_int(item) for item in _as_list(row, what="a 2-D array-like row")] for row in rows]


def to_label_list(value: object) -> list[Any]:
    """One 1-D numpy array of classification labels/predictions as a real Python
    `list` — e.g. `model.predict(X)` or `model.classes_`.

    Unlike the numeric helpers above, a label has no single concrete element type
    to validate against (a classification target's categories are typically
    strings, but nothing here requires that) — `SplitMatrix.y`/`ModelAdapter.predict`
    already declare `list[Any]` for the identical reason. This still confirms the
    one real invariant that matters: `tolist()` actually produced a `list`.
    """
    raw = _ensure_array(value, what="a 1-D array-like").tolist()
    return _as_list(raw, what="a 1-D array-like")


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


def compute_impurity_feature_importance(
    feature_columns: Sequence[str],
    importances: Sequence[float],
    *,
    normalized: bool = False,
) -> list[dict[str, Any]]:
    """Rank features by a tree ensemble's built-in impurity importances.

    `importances` is one non-negative value per feature — `sklearn`'s
    `RandomForestClassifier.feature_importances_` (mean decrease in impurity,
    normalized to sum to 1 across features). Unlike a linear model's
    coefficients there is no direction: a split on a feature reduces impurity
    regardless of which way the target moves, so `sign` is always `"neutral"`
    and `coefficient` carries the raw importance purely so the shared
    `feature_importance.csv` writer and `FeatureImportancePanel` render it
    unchanged. `abs_importance` (the ranking key, matching
    `compute_feature_importance`) is the importance itself.

    `normalized` is recorded per row exactly as in `compute_feature_importance`,
    though it matters far less here: impurity importance is invariant to any
    monotonic per-feature rescaling, so a z-scored and a raw run of the same
    forest rank features identically. It is still tagged so a reader can tell
    which dataset the run used without cross-referencing.
    """
    paired = list(zip(feature_columns, importances, strict=False))
    rows = [
        {
            "feature": name,
            "coefficient": float(importance),
            "abs_importance": float(importance),
            "sign": "neutral",
            "normalized": normalized,
        }
        for name, importance in paired
    ]
    rows.sort(key=lambda row: row["abs_importance"], reverse=True)
    return rows


def compute_permutation_importance(
    feature_columns: Sequence[str],
    model: Any,
    X: Any,  # noqa: N803 - matches SplitMatrix.X's own naming convention
    y: Sequence[Any],
    *,
    scoring: str = "accuracy",
    n_repeats: int = 10,
    random_state: int = 42,
    normalized: bool = False,
) -> list[dict[str, Any]]:
    """Rank features by permutation importance — the mean drop in `scoring`
    when one feature's column is independently shuffled, holding every
    other column fixed.

    The attribution method for a model with no native importance of its
    own — `HistGradientBoostingClassifier` exposes neither
    `feature_importances_` (that convention belongs to `RandomForestClassifier`
    and other bagged-tree ensembles, not boosting) nor `coef_` (linear models
    only). Permutation importance answers the same underlying question —
    "how much does this feature actually matter to a held-out prediction?" —
    by directly measuring it against a real, already-fitted model, rather
    than reading it off internal model structure that doesn't exist here.

    `X`/`y` must be a **held-out** split — `GradientBoostingAdapter.train()`
    calls this against `dataset.validation`, never `dataset.train`.
    Permutation importance computed on the training split would conflate
    "the model memorized this feature" with "this feature generalizes,"
    the exact distinction `compute_overfitting_flag` exists to catch
    elsewhere in this module.

    Like impurity importance (and unlike a linear coefficient), a permuted
    feature can only ever hurt held-out performance or leave it unchanged
    in expectation — there is no meaningful direction to report, so `sign`
    is always `"neutral"`, matching `compute_impurity_feature_importance`'s
    own convention. A *negative* mean importance (shuffling a feature
    happened to improve the score on this particular split — sampling
    noise, not signal) is reported as-is, never clamped to zero: it sorts
    to the bottom under the same descending-by-`abs_importance` order
    every other importance table uses, which is the correct place for "no
    evidence this feature contributes; possibly actively unhelpful" to
    land — clamping it to zero would make a mildly harmful feature
    indistinguishable from a genuinely irrelevant one.
    """
    from sklearn.inspection import permutation_importance
    from sklearn.utils import Bunch

    result = permutation_importance(
        model, X, list(y), scoring=scoring, n_repeats=n_repeats, random_state=random_state
    )
    # A single `scoring` string always yields one `Bunch` at runtime; the
    # stub's overload also covers a list-of-metrics call (-> dict[str,
    # Bunch]) and can't narrow on `scoring: str` alone, so this asserts the
    # real invariant explicitly rather than trusting the inferred type —
    # the same `assert isinstance(result, CursorResult)` narrowing
    # `app/repositories/backtest_runs.py`/`training.py` already use for an
    # analogous stub gap.
    assert isinstance(result, Bunch)
    means = to_float_list(result.importances_mean)
    rows = [
        {
            "feature": name,
            "coefficient": mean,
            "abs_importance": mean,
            "sign": "neutral",
            "normalized": normalized,
        }
        for name, mean in zip(feature_columns, means, strict=True)
    ]
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
        true_negative, false_positive, false_negative, true_positive = to_int_list(matrix.ravel())
        details.append(
            {
                "class": label,
                "true_positive": true_positive,
                "false_positive": false_positive,
                "true_negative": true_negative,
                "false_negative": false_negative,
                "support": true_positive + false_negative,
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
    # `sparse_output=False` is the default, but is named explicitly here so the
    # dense/sparse choice is pinned at the call site rather than left implicit —
    # `label_binarize` therefore never returns a scipy sparse matrix at runtime,
    # only the `ndarray | spmatrix` union sklearn's own stubs (where installed)
    # still describe (the stub doesn't encode the `sparse_output`-to-return-type
    # relationship). `to_float_matrix`'s own `_ensure_array` check confirms that
    # real invariant instead of assuming the union away.
    binarized = to_float_matrix(label_binarize(y_true, classes=labels, sparse_output=False))
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
        raw_fpr, raw_tpr, _ = roc_curve(column_true, column_score)
        raw_precision, raw_recall, _ = precision_recall_curve(column_true, column_score)
        false_positive_rate = to_float_list(raw_fpr)
        true_positive_rate = to_float_list(raw_tpr)
        curves[label] = {
            "roc": {"fpr": false_positive_rate, "tpr": true_positive_rate},
            "pr": {"precision": to_float_list(raw_precision), "recall": to_float_list(raw_recall)},
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
