"""Domain errors for the Live Prediction Service.

Only what's genuinely new to this module — a training job that has
completed with a real, serialized model but was never trained on real
data (so there is no `feature_columns`/`symbol`/`timeframe` recorded to
reconstruct a live feature vector from), and Prediction History's own
not-found/sort errors, mirroring `app/evaluation/errors.py`'s own
`BenchmarkRunNotFoundError`/`InvalidBenchmarkRunSortError` shape exactly.

Every other failure this service can hit already has a named error
elsewhere, reused rather than duplicated: a job that isn't completed yet or
has no artifact (`app.training.errors.PredictionNotAvailableError`, raised
by `TrainingJobService.predict` itself), an unknown market
(`app.services.market_query.MarketNotFoundError`), or too little candle
history for the requested features' warmup
(`app.services.market_query.CandleNotFoundError`).
"""

from fastapi import status

from app.core.exceptions import AppError


class LiveFeatureReconstructionNotSupportedError(AppError):
    """Raised when a training job has no recorded `feature_columns`/`target_column`
    (or its experiment has no recorded `feature_set`) to rebuild a live feature
    vector from — e.g. the `placeholder` adapter, which never trains on real data."""

    def __init__(self, job_id: object) -> None:
        super().__init__(
            f"Training job {job_id} was not trained on real data (no recorded "
            "feature_columns/target_column), so a live feature vector cannot be "
            "reconstructed for it",
            code="live_feature_reconstruction_not_supported",
            status_code=status.HTTP_409_CONFLICT,
        )


class PredictionRunNotFoundError(AppError):
    """Raised when the requested Prediction History run id does not exist."""

    def __init__(self, prediction_id: object) -> None:
        super().__init__(
            f"Prediction {prediction_id} not found",
            code="prediction_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class TrainingFeatureSetMismatchError(AppError):
    """Raised when a training job's recorded `feature_columns` no longer match
    what its experiment's *current* `feature_set` produces.

    Possible now that `ExperimentConfigDialog` lets `feature_set` be edited
    after a job has already trained (see `ARCHITECTURE.md` § "Experiment
    Management System") — a job's own model is frozen at whatever it
    trained on, so an edit made afterward can leave it unable to reconstruct
    a live feature vector until either the experiment's configuration is
    reverted or a new job is trained against the new one.
    """

    def __init__(self, job_id: object, missing_column: str) -> None:
        super().__init__(
            f"Training job {job_id}'s model expects feature column {missing_column!r}, "
            "which the experiment's current feature_set no longer produces — its "
            "configuration was likely edited after this job trained",
            code="training_feature_set_mismatch",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidPredictionSortError(AppError):
    """Raised when a Prediction History list request names an unsupported sort column."""

    def __init__(self, sort: str, direction: str, available: tuple[str, ...]) -> None:
        super().__init__(
            f"Invalid sort {sort!r}/{direction!r}. Available sort columns: "
            f"{', '.join(available)}; direction must be 'asc' or 'desc'",
            code="invalid_prediction_sort",
        )
