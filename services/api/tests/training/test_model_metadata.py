"""Tests for `app/training/model_metadata.py`'s `collect_model_metadata`."""

import joblib
import sklearn

from app.training.model_metadata import collect_model_metadata


class TestCollectModelMetadata:
    def test_reports_library_versions_and_run_shape(self) -> None:
        metadata = collect_model_metadata(
            feature_count=5,
            sample_count=100,
            training_duration_seconds=1.23456789,
            cpu_time_seconds=0.987654321,
        )

        assert metadata["sklearn_version"] == sklearn.__version__
        assert metadata["joblib_version"] == joblib.__version__
        assert metadata["feature_count"] == 5
        assert metadata["sample_count"] == 100
        assert metadata["training_duration_seconds"] == 1.234568
        assert metadata["cpu_time_seconds"] == 0.987654

    def test_reports_a_non_negative_memory_usage_on_this_posix_platform(self) -> None:
        metadata = collect_model_metadata(
            feature_count=1, sample_count=1, training_duration_seconds=0.0, cpu_time_seconds=0.0
        )

        assert metadata["memory_usage_mb"] is not None
        assert metadata["memory_usage_mb"] >= 0
