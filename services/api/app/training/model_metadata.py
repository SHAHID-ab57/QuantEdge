"""Model metadata collection — library versions, timing, memory, and dataset shape.

Recorded by every real (non-placeholder) adapter into its `TrainingResult.summary`
under the `"model_metadata"` key, alongside the existing metrics/confusion-matrix/
feature-importance content — purely additive to `TrainingResult`'s existing, already
generic `summary: dict[str, Any]` field.
"""

import sys
from typing import Any

import joblib
import sklearn


def collect_model_metadata(
    *,
    feature_count: int,
    sample_count: int,
    training_duration_seconds: float,
    cpu_time_seconds: float,
) -> dict[str, Any]:
    """Library versions plus this run's timing, memory, and dataset shape."""
    return {
        "sklearn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "training_duration_seconds": round(training_duration_seconds, 6),
        "cpu_time_seconds": round(cpu_time_seconds, 6),
        "memory_usage_mb": _peak_memory_mb(),
        "feature_count": feature_count,
        "sample_count": sample_count,
    }


def _peak_memory_mb() -> float | None:
    """Peak resident memory of this process so far, or `None` if unavailable.

    `resource` is POSIX-only (this platform's CI and deployment targets are both
    Linux); on any platform where the import fails, `memory_usage_mb` is honestly
    reported as unknown rather than fabricated.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - resource is POSIX-only, unreachable in CI
        return None

    peak_kilobytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports `ru_maxrss` in KB; macOS reports it in bytes.
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(peak_kilobytes / divisor, 3)
