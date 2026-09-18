"""Tests for the model serialization abstraction — save/load a fitted model."""

from pathlib import Path

import pytest
from sklearn.linear_model import LinearRegression

from app.training.serialization import LocalDiskModelSerializer, resolve_artifact_uri


class TestLocalDiskModelSerializer:
    def test_round_trips_a_fitted_model(self, tmp_path: Path) -> None:
        serializer = LocalDiskModelSerializer(tmp_path)
        model = LinearRegression()
        model.fit([[1.0], [2.0], [3.0]], [2.0, 4.0, 6.0])

        uri = serializer.save(model, "linear_regression")
        loaded = serializer.load(uri)

        assert loaded.predict([[4.0]])[0] == pytest.approx(8.0)

    def test_save_returns_a_bare_relative_filename_not_an_absolute_uri(
        self, tmp_path: Path
    ) -> None:
        """Regression coverage for the portability fix (STATE.md / production
        incident): a training machine's absolute path baked into `artifact_uri`
        is meaningless on any other machine, server included. `save()` must
        return something that still means the same thing on a different host —
        a bare filename, resolved fresh against *that* host's own
        `model_artifact_dir` at read time, never the writer's own absolute path.
        """
        serializer = LocalDiskModelSerializer(tmp_path)
        uri = serializer.save(LinearRegression(), "model")
        assert not uri.startswith("file://")
        assert "/" not in uri
        assert uri.endswith(".joblib")

    def test_each_save_gets_a_unique_uri(self, tmp_path: Path) -> None:
        serializer = LocalDiskModelSerializer(tmp_path)
        first = serializer.save(LinearRegression(), "model")
        second = serializer.save(LinearRegression(), "model")
        assert first != second

    def test_creates_the_directory_if_missing(self, tmp_path: Path) -> None:
        directory = tmp_path / "nested" / "model_artifacts"
        serializer = LocalDiskModelSerializer(directory)
        serializer.save(LinearRegression(), "model")
        assert directory.exists()

    def test_load_resolves_against_this_instances_own_directory_not_the_global_default(
        self, tmp_path: Path
    ) -> None:
        """A serializer built against a custom directory (every adapter unit
        test's own isolation — see tests/conftest.py's `_isolate_model_artifacts`)
        must keep resolving against *that* directory, not the process-wide
        `model_artifact_dir` setting — confirmed the hard way: an earlier version
        of this fix resolved every load through the global default unconditionally,
        which broke every test in this suite that isolates to its own `tmp_path`.
        """
        serializer = LocalDiskModelSerializer(tmp_path)
        uri = serializer.save(LinearRegression(), "model")
        assert resolve_artifact_uri(uri, base=tmp_path) == tmp_path / uri

    def test_legacy_absolute_file_uri_is_resolved_by_filename_only(self, tmp_path: Path) -> None:
        """A row written before this fix stored a real, absolute `file://` URI
        from the training machine's own filesystem — meaningless on any other
        host. Only its filename is trusted; the directory it names never is.
        """
        legacy_uri = "file:///some/other/machines/home/dir/model_artifacts/model-abc123.joblib"
        assert resolve_artifact_uri(legacy_uri, base=tmp_path) == tmp_path / "model-abc123.joblib"

    def test_legacy_absolute_report_file_uri_keeps_its_reports_prefix(self, tmp_path: Path) -> None:
        legacy_uri = "file:///some/other/machine/model_artifacts/reports/model-abc-metrics.json"
        assert (
            resolve_artifact_uri(legacy_uri, base=tmp_path)
            == tmp_path / "reports" / "model-abc-metrics.json"
        )
