"""Turns a built `MLDataset` into the `TrainingDataset` a real model adapter needs.

The one bridge between the ML Dataset Builder (`app/ml_datasets/`) and the
Training Framework's own `TrainingDataset` contract (`app/training/base.py`)
— nothing here builds features, generates targets, validates, or splits;
all of that is `MLDatasetBuilder`'s job, already done by the time an
`MLDataset` reaches this module. This module picks a target column,
restricts feature columns to numeric dtypes (categorical encoding is a
documented, not-yet-implemented extension point — see
`app/features/ai_extensions.py`'s `CategoricalEncoder`), optionally
normalizes every feature column (`normalize=True`, see
`app/training/normalization.py`), and reshapes each split's rows into a
`SplitMatrix`.

Normalization, when requested, runs in exactly one place in this whole
pipeline: `ColumnNormalizer.fit` against `ml_dataset.split.train` alone
(never validation/test — see that module's own docstring for why), and
`ColumnNormalizer.transform` against all three splits, **before** they are
converted into a `SplitMatrix` — a model adapter's own `train()` only ever
sees an already-normalized (or, if `normalize=False`, still-raw) numeric
matrix, and never has to know which.
"""

from app.features.base import FeatureValue
from app.features.dataset import FeatureDataset
from app.ml_datasets.dataset import MLDataset
from app.training.base import ModelKind, SplitMatrix, TrainingDataset
from app.training.errors import (
    EmptyTrainingSplitError,
    IncompatibleTargetDtypeError,
    NoNumericFeatureColumnsError,
    NoTargetColumnsError,
    UndefinedFeatureValueError,
    UnknownTargetColumnError,
)
from app.training.normalization import (
    DEFAULT_NORMALIZATION_METHOD,
    ColumnNormalizer,
    NormalizationMethod,
)

_NUMERIC_DTYPES = frozenset({"float", "int", "bool"})


def build_training_dataset(
    ml_dataset: MLDataset,
    *,
    model_kind: ModelKind,
    target_column: str | None = None,
    normalize: bool = False,
    normalization_method: NormalizationMethod = DEFAULT_NORMALIZATION_METHOD,
) -> TrainingDataset:
    """Resolve a target column and numeric feature columns, then build the three splits.

    `normalize=True` fits per-column statistics on `ml_dataset.split.train`
    alone and applies them to all three splits before they become numeric
    matrices — see this module's own docstring and
    `app/training/normalization.py` for the full rationale. Defaults `False`
    so a direct caller (a test, a future non-training consumer) gets the raw
    matrix unless it explicitly asks otherwise; `TrainingJobService` always
    passes an explicit value from the job's own `normalize_features` field.
    """
    if not ml_dataset.target_columns:
        raise NoTargetColumnsError()

    resolved_target = target_column or ml_dataset.target_columns[0]
    if resolved_target not in ml_dataset.target_columns:
        raise UnknownTargetColumnError(resolved_target, ml_dataset.target_columns)

    columns_by_name = {column.name: column for column in ml_dataset.dataset.columns}
    target_dtype = columns_by_name[resolved_target].dtype
    if model_kind == "regression" and target_dtype not in _NUMERIC_DTYPES:
        raise IncompatibleTargetDtypeError(model_kind, resolved_target, target_dtype)

    numeric_feature_columns = [
        name
        for name in ml_dataset.feature_columns
        if columns_by_name[name].dtype in _NUMERIC_DTYPES
    ]
    if not numeric_feature_columns:
        raise NoNumericFeatureColumnsError()

    column_index = {
        name: index
        for index, name in enumerate(column.name for column in ml_dataset.dataset.columns)
    }
    feature_indices = [column_index[name] for name in numeric_feature_columns]
    target_index = column_index[resolved_target]

    def to_numeric(value: FeatureValue, column: str, row_index: int) -> float:
        # Numeric-dtype feature columns are never `None`/`str` by the time
        # `drop_warmup`/`drop_undefined_targets` have run (both default `True` in
        # every request this module handles) — this only guards against that
        # upstream guarantee ever being violated, converting an otherwise-opaque
        # `TypeError` into a named, actionable domain error.
        if value is None or isinstance(value, str):
            raise UndefinedFeatureValueError(column, row_index)
        return float(value)

    def to_split_matrix(dataset: FeatureDataset, split_name: str) -> SplitMatrix:
        if dataset.row_count == 0:
            raise EmptyTrainingSplitError(split_name)
        X = [  # noqa: N806
            [
                to_numeric(row[index], numeric_feature_columns[position], row_index)
                for position, index in enumerate(feature_indices)
            ]
            for row_index, row in enumerate(dataset.rows)
        ]
        y = [row[target_index] for row in dataset.rows]
        return SplitMatrix(X=X, y=y)

    train_dataset = ml_dataset.split.train
    validation_dataset = ml_dataset.split.validation
    test_dataset = ml_dataset.split.test

    normalization_stats = None
    if normalize:
        normalizer = ColumnNormalizer(method=normalization_method)
        # Fit on the TRAIN split alone — see `ColumnNormalizer.fit`'s own
        # docstring for why validation/test must never influence these stats.
        normalization_stats = normalizer.fit(train_dataset, numeric_feature_columns)
        train_dataset = normalizer.transform(train_dataset, normalization_stats)
        validation_dataset = normalizer.transform(validation_dataset, normalization_stats)
        test_dataset = normalizer.transform(test_dataset, normalization_stats)

    return TrainingDataset(
        dataset_version=ml_dataset.ml_dataset_id,
        feature_columns=tuple(numeric_feature_columns),
        target_column=resolved_target,
        train=to_split_matrix(train_dataset, "train"),
        validation=to_split_matrix(validation_dataset, "validation"),
        test=to_split_matrix(test_dataset, "test"),
        normalization=normalization_stats,
        normalization_method=normalization_method if normalize else None,
    )
