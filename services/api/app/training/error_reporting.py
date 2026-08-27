"""Turns a raised training exception into a structured failure report.

`TrainingJobService.run()`'s except-block already turns any exception into
`error_message: str(exc)` on the failed job — this module builds a second, structured
`error_detail` (failure reason, affected feature, affected rows, a suggested fix)
alongside it, purely additive to that existing behavior. Uses `getattr` rather than
`isinstance` checks against every domain error class, since only a few
(`UndefinedFeatureValueError`) carry `column`/`row_index`, and this stays correct (just
less detailed) for an exception type it was never taught about.
"""

from typing import Any

#: One suggested fix per domain error `code` (see `app/training/errors.py`) — keyed by
#: `code` rather than exception class, since `AppError.code` is what a caller who only
#: has the serialized error already has.
_SUGGESTED_FIXES: dict[str, str] = {
    "missing_dataset_version": (
        "Set a dataset_version on this job, or record one on its linked experiment."
    ),
    "missing_training_data_source": (
        "Set both symbol and timeframe on this job before running it."
    ),
    "missing_feature_or_target_config": (
        "Record a feature_set and target_config on the linked experiment before running this job."
    ),
    "no_target_columns": ("Add at least one target to the linked experiment's target_config."),
    "unknown_target_column": (
        "Set target_column to one of the target columns the dataset build actually "
        "produced, or leave it blank to use the first one."
    ),
    "no_numeric_feature_columns": (
        "Select at least one numeric (float/int/bool) feature — categorical feature "
        "encoding is not implemented yet (see app/features/ai_extensions.py's "
        "CategoricalEncoder)."
    ),
    "undefined_feature_value": (
        "Check the upstream feature generator for this column; a numeric feature "
        "should never be null once warmup rows are dropped."
    ),
    "empty_training_split": (
        "Widen the candle range or adjust split ratios so every split has at least one row."
    ),
    "incompatible_target_dtype": (
        "Choose a target_column whose dtype matches this model's model_kind (numeric "
        "for regression, categorical for classification), or pick a different model "
        "adapter."
    ),
    "model_initialization_failed": "Check the hyperparameters passed to this model adapter.",
    "training_execution_failed": (
        "Check the model's hyperparameters and the shape of the input data."
    ),
}

_DEFAULT_SUGGESTED_FIX = "Review the job's logs for the exact stage and error, then retry."


def describe_training_failure(exc: Exception) -> dict[str, Any]:
    """Build `{reason, affected_feature, affected_rows, suggested_fix}` from `exc`."""
    row_index = getattr(exc, "row_index", None)
    code = getattr(exc, "code", None)
    suggested_fix = (
        _SUGGESTED_FIXES.get(code, _DEFAULT_SUGGESTED_FIX)
        if isinstance(code, str)
        else _DEFAULT_SUGGESTED_FIX
    )
    return {
        "reason": str(exc),
        "affected_feature": getattr(exc, "column", None),
        "affected_rows": [row_index] if isinstance(row_index, int) else None,
        "suggested_fix": suggested_fix,
    }
