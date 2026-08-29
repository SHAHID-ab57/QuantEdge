"""Domain errors for the Model Evaluation & Benchmarking Engine."""

from fastapi import status

from app.core.exceptions import AppError


class MetricNotFoundError(AppError):
    """Raised when a requested metric name is not in the registry."""

    def __init__(self, name: str, available: tuple[str, ...] = ()) -> None:
        options = ", ".join(available) if available else "(none registered)"
        super().__init__(
            f"Metric {name!r} is not registered. Available: {options}",
            code="metric_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
        self.name = name


class DuplicateMetricError(RuntimeError):
    """Raised at import time when two metrics claim the same registry name.

    Not an `AppError`: a programming mistake that must fail fast at startup,
    never a condition an HTTP client can trigger — the same split
    `DuplicateModelAdapterError`'s own module documents for its own registry.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"A metric named {name!r} is already registered")
        self.name = name


class NoBenchmarkTargetError(AppError):
    """Raised when a benchmark request names no dataset_version, target_column,
    or experiment_ids to compare — there is nothing to look up."""

    def __init__(self) -> None:
        super().__init__(
            "Provide at least one of dataset_version, target_column, or "
            "experiment_ids to compare training jobs",
            code="no_benchmark_target",
        )


class EmptyBenchmarkError(AppError):
    """Raised when a benchmark request matched zero completed training jobs."""

    def __init__(self) -> None:
        super().__init__(
            "No completed training jobs matched this benchmark request",
            code="empty_benchmark",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class BenchmarkRunNotFoundError(AppError):
    """Raised when a requested Benchmark History entry does not exist."""

    def __init__(self, run_id: object) -> None:
        super().__init__(
            f"Benchmark run {run_id} not found",
            code="benchmark_run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidBenchmarkRunSortError(AppError):
    """Raised when a Benchmark History list request names an unsupported sort column."""

    def __init__(self, sort: str, direction: str, available: tuple[str, ...]) -> None:
        super().__init__(
            f"Invalid sort {sort!r}/{direction!r}. Available sort columns: "
            f"{', '.join(available)}; direction must be 'asc' or 'desc'",
            code="invalid_benchmark_run_sort",
        )
