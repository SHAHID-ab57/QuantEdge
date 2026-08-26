"""ML dataset serialization — CSV and JSON, mirroring the Feature Engineering export design.

A separate `ExportFormat`/`EXPORT_FORMATS` registry from
`app.features.export`'s, not a reused one: Python dataclasses aren't
generic without extra machinery, and that module's `ExportFormat.serialize`
is typed `Callable[[FeatureDataset], str | bytes]` — reusing it as-is for
an `MLDataset` would be a type lie. What *is* reused is the pattern (a
format registered once, looked up by name rather than branched on) and the
small, genuinely-shared primitives (`iso_utc`, `safe_filename_part`,
`csv_cell` — promoted to public names in `app.features.export` for exactly
this reuse).

Every export is a **single flat file containing the full assembled
matrix** (features and targets as columns, one row per surviving candle)
**plus a `split` column** naming which of train/validation/test each row
belongs to — not three separate files. Since `MLDatasetBuilder` never
reorders rows, concatenating `split.train`, `split.validation`, and
`split.test` in that order reconstructs exactly `dataset` (the pre-split
matrix) with a parallel split label, so the one file is complete and needs
no cross-referencing to use correctly in, say, pandas
(``df[df.split == "train"]``).
"""

import csv
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.features.export import csv_cell, iso_utc, safe_filename_part
from app.ml_datasets.dataset import MLDataset


@dataclass(frozen=True, slots=True)
class ExportFormat:
    """One registered export format for an `MLDataset`."""

    extension: str
    media_type: str
    binary: bool
    serialize: Callable[[MLDataset], str | bytes]


def dataset_filename(ml_dataset: MLDataset, extension: str) -> str:
    """A stable, filesystem-safe name identifying what the file holds."""
    symbol = safe_filename_part(ml_dataset.dataset.symbol)
    timeframe = safe_filename_part(ml_dataset.dataset.timeframe)
    stamp = ml_dataset.created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{symbol}-{timeframe}-ml-dataset-{stamp}.{extension}"


def _split_labels(ml_dataset: MLDataset) -> list[str]:
    """One label per row of ``ml_dataset.dataset``, naming its split."""
    return (
        ["train"] * ml_dataset.split.train.row_count
        + ["validation"] * ml_dataset.split.validation.row_count
        + ["test"] * ml_dataset.split.test.row_count
    )


def to_csv(ml_dataset: MLDataset, *, include_metadata: bool = True) -> str:
    """Serialize as CSV: an optional metadata preamble, then the matrix plus a split column.

    The preamble is `#`-prefixed comment lines, the same convention
    `app.features.export.to_csv` uses, for the same reason: the file still
    loads with a plain ``read_csv(..., comment='#')`` while remaining
    readable to a human.
    """
    dataset = ml_dataset.dataset
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    if include_metadata:
        for key, value in _metadata_pairs(ml_dataset):
            buffer.write(f"# {key},{value}\n")
        for target_line in _target_metadata_lines(ml_dataset):
            buffer.write(f"# {target_line}\n")
        for quality_line in _quality_lines(ml_dataset):
            buffer.write(f"# {quality_line}\n")
        buffer.write(
            f"# validation,passed={ml_dataset.validation.passed} "
            f"errors={ml_dataset.validation.summary.errors} "
            f"warnings={ml_dataset.validation.summary.warnings}\n"
        )

    writer.writerow(["timestamp", *(column.name for column in dataset.columns), "split"])
    for timestamp, row, split_label in zip(
        dataset.timestamps, dataset.rows, _split_labels(ml_dataset), strict=True
    ):
        writer.writerow([iso_utc(timestamp), *(csv_cell(value) for value in row), split_label])

    return buffer.getvalue()


def to_json(ml_dataset: MLDataset) -> str:
    """Serialize as JSON with full provenance: features, targets, split, and validation."""
    dataset = ml_dataset.dataset
    payload: dict[str, Any] = {
        "ml_dataset_id": ml_dataset.ml_dataset_id,
        "dataset_id": dataset.dataset_id,
        "symbol": dataset.symbol,
        "timeframe": dataset.timeframe,
        "generated_at": iso_utc(dataset.generated_at),
        "exported_at": iso_utc(datetime.now(UTC)),
        "pipeline_version": dataset.pipeline_version,
        "target_pipeline_version": ml_dataset.target_pipeline_version,
        "builder_version": ml_dataset.builder_version,
        "feature_columns": list(ml_dataset.feature_columns),
        "target_columns": list(ml_dataset.target_columns),
        "columns": [
            {
                "name": column.name,
                "label": column.label,
                "description": column.description,
                "dtype": column.dtype,
            }
            for column in dataset.columns
        ],
        "features": [
            {
                "feature": info.feature,
                "label": info.label,
                "version": info.version,
                "params": info.params,
                "columns": info.columns,
                "warmup": info.warmup,
            }
            for info in dataset.features
        ],
        "targets": [
            {
                "target": info.target,
                "label": info.label,
                "version": info.version,
                "params": info.params,
                "columns": info.columns,
                "horizon": info.horizon,
            }
            for info in ml_dataset.targets
        ],
        "split_ratios": {
            "train": ml_dataset.split_ratios.train,
            "validation": ml_dataset.split_ratios.validation,
            "test": ml_dataset.split_ratios.test,
        },
        "split_bounds": {
            "train_rows": ml_dataset.split.train.row_count,
            "validation_rows": ml_dataset.split.validation.row_count,
            "test_rows": ml_dataset.split.test.row_count,
        },
        "validation": {
            "passed": ml_dataset.validation.passed,
            "engine_version": ml_dataset.validation.engine_version,
            "summary": {
                "total_checks": ml_dataset.validation.summary.total_checks,
                "errors": ml_dataset.validation.summary.errors,
                "warnings": ml_dataset.validation.summary.warnings,
                "info": ml_dataset.validation.summary.info,
            },
            "issues": [
                {
                    "rule": issue.rule,
                    "category": issue.category,
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in ml_dataset.validation.issues
            ],
        },
        "meta": {
            "row_count": dataset.row_count,
            "candles_analyzed": dataset.candles_analyzed,
            "rows_dropped_warmup": dataset.rows_dropped,
            "rows_dropped_horizon": ml_dataset.rows_dropped_for_horizon,
            "warmup_candles": dataset.warmup_candles,
            "max_horizon": ml_dataset.max_horizon,
        },
        "data": [
            {
                "timestamp": iso_utc(timestamp),
                **{column.name: row[index] for index, column in enumerate(dataset.columns)},
                "split": split_label,
            }
            for timestamp, row, split_label in zip(
                dataset.timestamps, dataset.rows, _split_labels(ml_dataset), strict=True
            )
        ],
    }
    return json.dumps(payload, indent=2, default=str)


#: Every export format this endpoint accepts, keyed by the wire name
#: (``?format=csv``) — adding Parquet later is one new entry here, mirroring
#: `app.features.export.EXPORT_FORMATS` exactly.
EXPORT_FORMATS: dict[str, ExportFormat] = {
    "csv": ExportFormat(
        extension="csv", media_type="text/csv; charset=utf-8", binary=False, serialize=to_csv
    ),
    "json": ExportFormat(
        extension="json",
        media_type="application/json; charset=utf-8",
        binary=False,
        serialize=to_json,
    ),
}


def _metadata_pairs(ml_dataset: MLDataset) -> list[tuple[str, str]]:
    """The provenance lines written above a CSV matrix."""
    dataset = ml_dataset.dataset
    return [
        ("ml_dataset_id", ml_dataset.ml_dataset_id),
        ("dataset_id", dataset.dataset_id),
        ("symbol", dataset.symbol),
        ("timeframe", dataset.timeframe),
        ("generated_at", iso_utc(dataset.generated_at)),
        ("exported_at", iso_utc(datetime.now(UTC))),
        ("pipeline_version", dataset.pipeline_version),
        ("target_pipeline_version", ml_dataset.target_pipeline_version),
        ("builder_version", ml_dataset.builder_version),
        ("rows", str(dataset.row_count)),
        ("rows_dropped_warmup", str(dataset.rows_dropped)),
        ("rows_dropped_horizon", str(ml_dataset.rows_dropped_for_horizon)),
        ("split_train_rows", str(ml_dataset.split.train.row_count)),
        ("split_validation_rows", str(ml_dataset.split.validation.row_count)),
        ("split_test_rows", str(ml_dataset.split.test.row_count)),
    ]


def _target_metadata_lines(ml_dataset: MLDataset) -> list[str]:
    """One CSV comment line per requested target, naming its full provenance."""
    return [
        f"target.{info.target},version={info.version} horizon={info.horizon} "
        f"columns=({','.join(info.columns)})"
        for info in ml_dataset.targets
    ]


def _quality_lines(ml_dataset: MLDataset) -> list[str]:
    """CSV comment lines summarizing the assembled dataset's quality and validation."""
    quality = ml_dataset.dataset.quality
    lines = [
        f"quality.duplicate_timestamps,{quality.duplicate_timestamps}",
        f"quality.missing_candles,{quality.missing_candles}",
    ]
    for failure in quality.feature_failures:
        lines.append(f"quality.generation_failure,{failure.feature}: {failure.error_detail}")
    return lines
