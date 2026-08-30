"""Per-column feature normalization — this platform's first real implementer
of `app.features.ai_extensions.FeatureNormalizer`.

Fixes two concrete problems, not just a missing capability:

1. Feature Importance (mean absolute coefficient) is scale-biased. A feature
   naturally measured in the thousands (`close`, `sma_20`) needs only a tiny
   coefficient to contribute as much to a linear/logistic decision boundary
   as an equally predictive feature measured in single digits
   (`candle_body`) needs a much larger one — so ranking by raw coefficient
   magnitude alone systematically undervalues large-scale features.
2. L2 regularization (`C`) penalizes a coefficient's own squared magnitude,
   which implicitly under-penalizes (and therefore over-relies on)
   large-magnitude features relative to their real contribution, for the
   identical reason.

`ColumnNormalizer` fits per-column statistics from one `FeatureDataset` (the
caller's job to ensure this is the TRAIN split only — see
`app/training/dataset_loader.py`, the one place this is wired in) and
applies them to transform any `FeatureDataset` sharing the same columns —
train, validation, test alike. `apply_normalization` is the same transform
over a plain numeric matrix, for a live prediction request's raw rows,
which carry no columns/timestamps/quality report to build a `FeatureDataset`
from.

Deliberately a training-time concern: `FeatureDatasetRequest`/
`FeatureDatasetResponse` (the Feature Engineering Engine's own contract) and
every ML Dataset Builder export/history entry stay raw and human-readable —
nothing here touches those. This module only ever runs between
`ChronologicalSplitter` (which needs to know train/validation/test
membership first) and a model adapter's own `train()`/`predict()`.
"""

from collections.abc import Sequence
from dataclasses import replace
from typing import Literal

from app.features.ai_extensions import NormalizationStats
from app.features.dataset import FeatureDataset

NormalizationMethod = Literal["zscore", "minmax"]

#: Z-score is the default — the conventional choice for a linear/logistic
#: model whose regularization term is scale-sensitive (see this module's own
#: docstring, point 2). Min-max is fully implemented and correct but not
#: wired to any request-time choice today; a future selector would pass
#: `"minmax"` through with no change needed here.
DEFAULT_NORMALIZATION_METHOD: NormalizationMethod = "zscore"


def _transform_value(value: float, stats: NormalizationStats, method: NormalizationMethod) -> float:
    """Transform a single numeric value using one column's fitted stats.

    A zero-variance (or zero-range) column reports `0.0` rather than
    dividing by zero or fabricating a value — the same "a constant column
    has no signal, 0.0 is the honest answer" convention
    `app/features/correlation.py`'s `_pearson` already established for the
    identical degenerate case.
    """
    if method == "minmax":
        if stats.minimum is None or stats.maximum is None or stats.maximum == stats.minimum:
            return 0.0
        return (value - stats.minimum) / (stats.maximum - stats.minimum)
    if stats.mean is None or stats.std is None or stats.std == 0.0:
        return 0.0
    return (value - stats.mean) / stats.std


class ColumnNormalizer:
    """Fits per-column statistics on one dataset, applies them to another.

    Implements `app.features.ai_extensions.FeatureNormalizer` (`fit`/
    `transform`, same signatures) — the Protocol's first real implementer.
    Holds no mutable state beyond its own immutable `method`, the same
    stateless posture every other engine component on this platform takes.
    """

    def __init__(self, method: NormalizationMethod = DEFAULT_NORMALIZATION_METHOD) -> None:
        self._method: NormalizationMethod = method

    @property
    def method(self) -> NormalizationMethod:
        """Which transform `transform()` applies — `"zscore"` or `"minmax"`."""
        return self._method

    def fit(self, dataset: FeatureDataset, columns: Sequence[str]) -> list[NormalizationStats]:
        """Compute mean/std/min/max for each of `columns`, from `dataset` alone.

        The caller is responsible for passing only the TRAIN split —
        computing these statistics from validation/test rows would leak
        held-out information into every value a model ever sees, the same
        category of look-ahead bias chronological splitting already exists
        to prevent (see `app/ml_datasets/split.py`'s own module docstring).
        Always computes all four statistics regardless of `method`, so a
        fitted `NormalizationStats` remains meaningful reference data even
        if a future caller re-applies it under the other method.
        """
        index_by_name = {column.name: index for index, column in enumerate(dataset.columns)}
        stats: list[NormalizationStats] = []
        for name in columns:
            index = index_by_name[name]
            values = _numeric_column_values(dataset, index)
            if not values:
                stats.append(NormalizationStats(column=name))
                continue
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            stats.append(
                NormalizationStats(
                    column=name,
                    mean=mean,
                    std=variance**0.5,
                    minimum=min(values),
                    maximum=max(values),
                )
            )
        return stats

    def transform(
        self, dataset: FeatureDataset, stats: Sequence[NormalizationStats]
    ) -> FeatureDataset:
        """Apply already-fit `stats` to every named column in `dataset`.

        A column named in `stats` that isn't present in `dataset.columns` is
        skipped rather than raising — the same tolerant-by-default posture
        `correlation.py`/`statistics.py` already take toward a dataset shape
        they don't fully recognize. A cell that isn't numeric is left
        untouched (never fabricated), the same "honest, never invented"
        contract this platform's other per-cell transforms already hold.
        """
        index_by_name = {column.name: index for index, column in enumerate(dataset.columns)}
        rows = [list(row) for row in dataset.rows]
        for entry in stats:
            index = index_by_name.get(entry.column)
            if index is None:
                continue
            for row in rows:
                value = row[index]
                if not isinstance(value, int | float):
                    continue
                row[index] = _transform_value(float(value), entry, self._method)
        return replace(dataset, rows=rows)


def apply_normalization(
    rows: Sequence[Sequence[float]],
    stats: Sequence[NormalizationStats],
    *,
    method: NormalizationMethod = DEFAULT_NORMALIZATION_METHOD,
) -> list[list[float]]:
    """Transform already-numeric rows (one row per example, one column per
    `stats` entry, in the same order) using already-fit `stats`.

    The one seam `TrainingJobService.predict` uses to apply the identical
    transform a completed job trained with to a caller-supplied prediction
    row — a `SplitMatrix.X`-shaped input, not a whole `FeatureDataset`
    (a live prediction request has no columns/timestamps/quality report to
    carry, only the numeric feature values themselves).
    """
    return [
        [
            _transform_value(float(value), entry, method)
            for value, entry in zip(row, stats, strict=True)
        ]
        for row in rows
    ]


def _numeric_column_values(dataset: FeatureDataset, index: int) -> list[float]:
    """Every numeric (int/float/bool) value in one column, in row order."""
    values: list[float] = []
    for row in dataset.rows:
        value = row[index]
        if isinstance(value, int | float):
            values.append(float(value))
    return values


def normalization_stats_to_dicts(
    stats: Sequence[NormalizationStats] | None,
) -> list[dict[str, str | float | None]] | None:
    """Plain, JSON-serializable form of `fit()`'s output — `None` passes through.

    `NormalizationStats` is a dataclass, not natively JSON-serializable by
    SQLAlchemy's `JSON` column type — every real model adapter uses this to
    record its `TrainingDataset.normalization` onto `TrainingResult.summary`
    (persisted verbatim as `TrainingJob.result_summary`), and
    `TrainingJobService.predict` reconstructs `NormalizationStats` instances
    from the identical shape via `NormalizationStats(**entry)`.
    """
    if stats is None:
        return None
    return [
        {
            "column": entry.column,
            "mean": entry.mean,
            "std": entry.std,
            "minimum": entry.minimum,
            "maximum": entry.maximum,
        }
        for entry in stats
    ]
