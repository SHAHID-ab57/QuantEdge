"""Tests for `app/training/artifact_files.py` — the downloadable training-run
report artifacts (metrics.json, training_report.json, feature_importance.csv,
confusion_matrix.png, roc_curve.png, precision_recall_curve.png).

Deliberately separate from `test_serialization.py`: these functions write plain
report files, never reloaded by any model adapter, and are not part of the
`ModelSerializer` abstraction those tests cover.
"""

import json
from pathlib import Path

import pytest

from app.training import artifact_files


@pytest.fixture(autouse=True)
def _reports_into_tmp_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every `write_*` function resolves its directory via `_reports_directory()` —
    redirect it to a per-test `tmp_path` so nothing here touches the real
    `var/model_artifacts/reports` directory."""
    monkeypatch.setattr(artifact_files, "_reports_directory", lambda: tmp_path)


def _read(uri: str) -> bytes:
    assert uri.startswith("file://")
    return Path.from_uri(uri).read_bytes()


class TestWriteMetricsJson:
    def test_writes_a_readable_json_file(self) -> None:
        uri = artifact_files.write_metrics_json("logistic_regression", {"accuracy": 0.9})

        assert uri.endswith(".json")
        assert json.loads(_read(uri)) == {"accuracy": 0.9}


class TestWriteTrainingReportJson:
    def test_writes_a_readable_json_file(self) -> None:
        uri = artifact_files.write_training_report_json(
            "linear_regression", {"n_train": 10, "feature_columns": ["open"]}
        )

        assert json.loads(_read(uri))["n_train"] == 10


class TestWriteFeatureImportanceCsv:
    def test_writes_a_header_and_one_row_per_feature(self) -> None:
        rows = [
            {
                "feature": "open",
                "coefficient": 0.5,
                "abs_importance": 0.5,
                "sign": "positive",
                "normalized": True,
            },
            {
                "feature": "close",
                "coefficient": -0.2,
                "abs_importance": 0.2,
                "sign": "negative",
                "normalized": True,
            },
        ]

        uri = artifact_files.write_feature_importance_csv("logistic_regression", rows)
        lines = _read(uri).decode().splitlines()

        assert lines[0] == "feature,coefficient,abs_importance,sign,normalized"
        assert lines[1] == "open,0.5,0.5,positive,True"
        assert lines[2] == "close,-0.2,0.2,negative,True"

    def test_tolerates_a_row_missing_the_normalized_key(self) -> None:
        """A report recorded before `normalized` existed still writes a valid
        (if blank in that column) CSV rather than raising."""
        rows = [{"feature": "open", "coefficient": 0.5, "abs_importance": 0.5, "sign": "positive"}]

        uri = artifact_files.write_feature_importance_csv("logistic_regression", rows)
        lines = _read(uri).decode().splitlines()

        assert lines[1] == "open,0.5,0.5,positive,"


class TestWriteConfusionMatrixPng:
    def test_writes_a_non_empty_png_file(self) -> None:
        uri = artifact_files.write_confusion_matrix_png(
            "logistic_regression", [[5, 1], [2, 4]], ["down", "up"]
        )

        data = _read(uri)
        assert uri.endswith(".png")
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


class TestWriteRocCurvePng:
    def test_writes_a_non_empty_png_file(self) -> None:
        curves = {
            "up": {
                "roc": {"fpr": [0.0, 1.0], "tpr": [0.0, 1.0]},
                "pr": {"precision": [1.0, 0.5], "recall": [0.0, 1.0]},
            },
        }
        uri = artifact_files.write_roc_curve_png("logistic_regression", curves, {"up": 0.9})

        assert _read(uri)[:8] == b"\x89PNG\r\n\x1a\n"


class TestWritePrecisionRecallCurvePng:
    def test_writes_a_non_empty_png_file(self) -> None:
        curves = {
            "up": {
                "roc": {"fpr": [0.0, 1.0], "tpr": [0.0, 1.0]},
                "pr": {"precision": [1.0, 0.5], "recall": [0.0, 1.0]},
            },
        }
        uri = artifact_files.write_precision_recall_curve_png("logistic_regression", curves)

        assert _read(uri)[:8] == b"\x89PNG\r\n\x1a\n"
