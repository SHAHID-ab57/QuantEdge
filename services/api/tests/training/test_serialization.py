"""Tests for the model serialization abstraction — save/load a fitted model."""

from pathlib import Path

import pytest
from sklearn.linear_model import LinearRegression

from app.training.serialization import LocalDiskModelSerializer


class TestLocalDiskModelSerializer:
    def test_round_trips_a_fitted_model(self, tmp_path: Path) -> None:
        serializer = LocalDiskModelSerializer(tmp_path)
        model = LinearRegression()
        model.fit([[1.0], [2.0], [3.0]], [2.0, 4.0, 6.0])

        uri = serializer.save(model, "linear_regression")
        loaded = serializer.load(uri)

        assert loaded.predict([[4.0]])[0] == pytest.approx(8.0)

    def test_save_returns_a_file_uri(self, tmp_path: Path) -> None:
        serializer = LocalDiskModelSerializer(tmp_path)
        uri = serializer.save(LinearRegression(), "model")
        assert uri.startswith("file://")

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

    def test_rejects_a_non_file_uri(self, tmp_path: Path) -> None:
        serializer = LocalDiskModelSerializer(tmp_path)
        with pytest.raises(ValueError, match="file://"):
            serializer.load("https://example.com/model.joblib")
