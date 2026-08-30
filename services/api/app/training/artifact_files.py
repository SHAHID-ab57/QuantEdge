"""Writes downloadable training-run report artifacts to local disk.

Deliberately a separate module from `app/training/serialization.py`'s
`ModelSerializer` abstraction (untouched by this module): `ModelSerializer` only ever
saves/loads a *model object* so `predict()` can reload it later — these functions
write plain report files (JSON/CSV/PNG) a researcher downloads to inspect a run, never
reloaded by any adapter. Both happen to live under the same
`Settings.model_artifact_dir` root (a `reports/` subdirectory here) purely so one
setting controls where this platform's training-run output goes; nothing here imports
from or extends `serialization.py`.

Every `write_*` function returns a `file://` URI, exactly like `LocalDiskModelSerializer.save`,
so `TrainingJobService`'s artifact-download endpoint resolves every artifact type
(model included) through the same `Path.from_uri(uri)` logic.
"""

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless — no display server exists in this API process

import matplotlib.pyplot as plt  # noqa: E402 - backend must be selected before this import

from app.core.config import get_settings


def _reports_directory() -> Path:
    configured = get_settings().model_artifact_dir
    base = Path(configured)
    base = base if base.is_absolute() else Path.cwd() / base
    return base / "reports"


def _write_bytes(name: str, suffix: str, data: bytes) -> str:
    directory = _reports_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}-{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)
    return path.resolve().as_uri()


def write_metrics_json(name: str, metrics: dict[str, Any]) -> str:
    """`metrics.json` — every metric this run recorded (train/validation/test)."""
    return _write_bytes(name, "-metrics.json", json.dumps(metrics, indent=2, default=str).encode())


def write_training_report_json(name: str, report: dict[str, Any]) -> str:
    """`training_report.json` — the full result summary: hyperparameters, dataset
    shape, timing/memory, and every other field this run's adapter recorded."""
    return _write_bytes(
        name, "-training_report.json", json.dumps(report, indent=2, default=str).encode()
    )


def write_feature_importance_csv(name: str, rows: list[dict[str, Any]]) -> str:
    """`feature_importance.csv` — one row per feature, ranked by absolute importance."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["feature", "coefficient", "abs_importance", "sign", "normalized"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return _write_bytes(name, "-feature_importance.csv", buffer.getvalue().encode())


def write_confusion_matrix_png(name: str, matrix: list[list[int]], classes: list[str]) -> str:
    """`confusion_matrix.png` — a labeled heatmap of the raw confusion matrix."""
    figure, axes = plt.subplots(figsize=(4.5, 4.5))
    axes.imshow(matrix, cmap="Blues")
    axes.set_xticks(range(len(classes)))
    axes.set_yticks(range(len(classes)))
    axes.set_xticklabels(classes)
    axes.set_yticklabels(classes)
    axes.set_xlabel("Predicted")
    axes.set_ylabel("Actual")
    axes.set_title("Confusion Matrix")
    for row_index, row in enumerate(matrix):
        for column_index, value in enumerate(row):
            axes.text(column_index, row_index, str(value), ha="center", va="center")
    figure.tight_layout()
    return _savefig(figure, name, "-confusion_matrix.png")


def write_roc_curve_png(
    name: str, curves: dict[Any, dict[str, Any]], auc_scores: dict[Any, float]
) -> str:
    """`roc_curve.png` — one-vs-rest ROC curve per class, each labeled with its AUC."""
    figure, axes = plt.subplots(figsize=(5, 4.5))
    for label, curve in curves.items():
        auc_score = auc_scores.get(label, 0.0)
        axes.plot(curve["roc"]["fpr"], curve["roc"]["tpr"], label=f"{label} (AUC={auc_score:.3f})")
    axes.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Chance")
    axes.set_xlabel("False Positive Rate")
    axes.set_ylabel("True Positive Rate")
    axes.set_title("ROC Curve")
    axes.legend(loc="lower right", fontsize="small")
    figure.tight_layout()
    return _savefig(figure, name, "-roc_curve.png")


def write_precision_recall_curve_png(name: str, curves: dict[Any, dict[str, Any]]) -> str:
    """`precision_recall_curve.png` — one-vs-rest Precision-Recall curve per class."""
    figure, axes = plt.subplots(figsize=(5, 4.5))
    for label, curve in curves.items():
        axes.plot(curve["pr"]["recall"], curve["pr"]["precision"], label=str(label))
    axes.set_xlabel("Recall")
    axes.set_ylabel("Precision")
    axes.set_title("Precision-Recall Curve")
    axes.legend(loc="lower left", fontsize="small")
    figure.tight_layout()
    return _savefig(figure, name, "-precision_recall_curve.png")


def _savefig(figure: Any, name: str, suffix: str) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    return _write_bytes(name, suffix, buffer.getvalue())
