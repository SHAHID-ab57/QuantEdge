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
