"""Domain errors for the Machine Learning Training Framework."""

from fastapi import status

from app.core.exceptions import AppError


class InvalidTrainingJobTransitionError(AppError):
    """Raised when a requested status transition is not a legal lifecycle move."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Cannot move a training job from {current!r} to {target!r}",
            code="invalid_training_job_transition",
            status_code=status.HTTP_409_CONFLICT,
        )


class TrainingJobNotFoundError(AppError):
    """Raised when the requested training job id does not exist."""

    def __init__(self, job_id: object) -> None:
        super().__init__(
            f"Training job {job_id} not found",
            code="training_job_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ModelAdapterNotFoundError(AppError):
    """Raised when a training job names a `model_type` with no registered adapter."""

    def __init__(self, name: str, available: tuple[str, ...]) -> None:
        options = ", ".join(available) if available else "(none registered)"
        super().__init__(
            f"Unknown model adapter {name!r}. Available: {options}",
            code="model_adapter_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class DuplicateModelAdapterError(AppError):
    """Raised when two model adapters register under the same name."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"A model adapter named {name!r} is already registered",
            code="duplicate_model_adapter",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class MissingDatasetVersionError(AppError):
    """Raised when a job (and its linked experiment) has no dataset citation to train over."""

    def __init__(self) -> None:
        super().__init__(
            "This job has no dataset_version, and its experiment does not record one either; "
            "a training job must cite the dataset it trains over",
            code="missing_dataset_version",
        )


class MissingTrainingDataSourceError(AppError):
    """Raised when a `requires_real_data` adapter is used but the job has no
    symbol/timeframe to load real candles from."""

    def __init__(self) -> None:
        super().__init__(
            "This model adapter requires real training data, but the job has no "
            "symbol/timeframe recorded to build a dataset from",
            code="missing_training_data_source",
        )


class MissingFeatureOrTargetConfigError(AppError):
    """Raised when a `requires_real_data` adapter is used but the linked experiment
    has no recorded feature_set/target_config to build a dataset from."""

    def __init__(self) -> None:
        super().__init__(
            "This model adapter requires real training data, but the linked experiment "
            "has no recorded feature_set/target_config to build a dataset from",
            code="missing_feature_or_target_config",
        )


class NoTargetColumnsError(AppError):
    """Raised when the built ML dataset produced no target columns at all."""

    def __init__(self) -> None:
        super().__init__(
            "The built dataset has no target columns to train against",
            code="no_target_columns",
        )


class UnknownTargetColumnError(AppError):
    """Raised when a job's `target_column` override does not match any column the
    built dataset actually produced."""

    def __init__(self, target_column: str, available: tuple[str, ...]) -> None:
        options = ", ".join(available) if available else "(none)"
        super().__init__(
            f"Unknown target_column {target_column!r}. Available: {options}",
            code="unknown_target_column",
        )


class NoNumericFeatureColumnsError(AppError):
    """Raised when every requested feature resolved to a categorical column,
    leaving nothing numeric for a baseline model to train on."""

    def __init__(self) -> None:
        super().__init__(
            "None of this dataset's feature columns are numeric (float/int/bool); "
            "categorical feature encoding is not implemented yet "
            "(see app/features/ai_extensions.py's CategoricalEncoder)",
            code="no_numeric_feature_columns",
        )


class UndefinedFeatureValueError(AppError):
    """Raised when a numeric-dtype feature column unexpectedly holds a `None`/string
    value at training time — should never happen given `drop_warmup`/
    `drop_undefined_targets` default to `True`, but converted into a named error
    rather than an opaque `TypeError` if it ever does.

    Carries `column`/`row_index` as plain attributes (not just baked into the message)
    so `app/training/error_reporting.py` can report "affected feature"/"affected rows"
    structurally, without parsing the message text.
    """

    def __init__(self, column: str, row_index: int | None = None) -> None:
        super().__init__(
            f"Feature column {column!r} has an undefined or non-numeric value where a "
            f"number was expected (row {row_index})"
            if row_index is not None
            else f"Feature column {column!r} has an undefined or non-numeric value where a "
            "number was expected",
            code="undefined_feature_value",
        )
        self.column = column
        self.row_index = row_index


class EmptyTrainingSplitError(AppError):
    """Raised when the train or validation split has zero rows, e.g. because the
    candle range loaded was too small for the requested split ratios."""

    def __init__(self, split_name: str) -> None:
        super().__init__(
            f"The {split_name} split has zero rows — widen the candle range or "
            "adjust the split ratios",
            code="empty_training_split",
        )


class IncompatibleTargetDtypeError(AppError):
    """Raised when a regression adapter is given a categorical target, or a
    classification adapter's target dtype can't be inferred."""

    def __init__(self, model_kind: str, target_column: str, dtype: str) -> None:
        super().__init__(
            f"Model kind {model_kind!r} is not compatible with target column "
            f"{target_column!r}'s dtype {dtype!r}",
            code="incompatible_target_dtype",
        )


class InvalidTrainingJobSortError(AppError):
    """Raised when the sort column or direction is unsupported."""

    def __init__(self, sort: str, direction: str, columns: tuple[str, ...]) -> None:
        options = ", ".join(sorted(columns))
        super().__init__(
            f"Unsupported sort {sort!r} (direction {direction!r}); "
            f"supported columns: {options}, directions: asc, desc",
            code="invalid_sort",
        )


class TrainingJobNotCancellableError(AppError):
    """Raised when deleting or cancelling a job whose lifecycle forbids it right now."""

    def __init__(self, job_id: object, status_: str) -> None:
        super().__init__(
            f"Training job {job_id} cannot be modified while status is {status_!r}",
            code="training_job_not_cancellable",
            status_code=status.HTTP_409_CONFLICT,
        )


class ModelInitializationError(AppError):
    """Raised when a model adapter's `initialize` raises."""

    def __init__(self, adapter: str, detail: str) -> None:
        super().__init__(
            f"Model adapter {adapter!r} failed to initialize: {detail}",
            code="model_initialization_failed",
        )


class TrainingExecutionError(AppError):
    """Raised when a model adapter's `train` raises."""

    def __init__(self, adapter: str, detail: str) -> None:
        super().__init__(
            f"Model adapter {adapter!r} failed during training: {detail}",
            code="training_execution_failed",
        )


class PredictionNotAvailableError(AppError):
    """Raised when a job has no completed, serialized model to predict with yet."""

    def __init__(self, job_id: object, status_: str) -> None:
        super().__init__(
            f"Training job {job_id} has no trained model available for prediction "
            f"(status is {status_!r}; a job must be completed)",
            code="prediction_not_available",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidPredictionInputError(AppError):
    """Raised when a prediction request's rows don't match the model's feature column count."""

    def __init__(self, expected_columns: int) -> None:
        super().__init__(
            f"Every row must have exactly {expected_columns} values, matching this "
            "job's feature_columns",
            code="invalid_prediction_input",
        )


class TrainingArtifactNotFoundError(AppError):
    """Raised when a job has no artifact of the requested type, or its file is
    missing from disk."""

    def __init__(self, job_id: object, artifact_type: str) -> None:
        super().__init__(
            f"Training job {job_id} has no {artifact_type!r} artifact available",
            code="training_artifact_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class PredictionExecutionError(AppError):
    """Raised when a model adapter's `predict` raises."""

    def __init__(self, adapter: str, detail: str) -> None:
        super().__init__(
            f"Model adapter {adapter!r} failed during prediction: {detail}",
            code="prediction_execution_failed",
        )
