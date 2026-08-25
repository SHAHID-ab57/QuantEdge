"""Dataset serialization — CSV and JSON, with Parquet as a documented extension point.

Export lives on the backend rather than the frontend, and that is a
deliberate split from how the History page exports candles (client-side,
from data it already has). The reason is that a *preview* and an *export*
are not the same data: the preview is deliberately truncated to a few
hundred rows so a browser can render it, while an export must contain the
whole dataset. Building the export from the preview would silently ship a
truncated training set — the single most damaging thing an export button
can do.

Every format carries the same provenance: the dataset id, generation
timestamp, *export* timestamp (when the file was serialized — distinct
from when the dataset itself was built, should a future cached-dataset
lookup make the two moments differ), pipeline version, every feature's
full metadata (not just name/version — unit, value type, dependencies,
determinism), and the quality report. An exported file that cannot say
which pipeline version, feature versions, and resolved parameters produced
it is not reproducible, and D6/D7 require reproducibility.

Pure functions over a ``FeatureDataset``: no DOM, no HTTP, no filesystem,
so every format is testable without a client and a future artifact store
can reuse them unchanged.

**Adding Parquet requires no change to this module's callers.** ``EXPORT_FORMATS``
is the one place a format is registered; `FeatureService.export_dataset` and
the `/features/export` endpoint both look a format up by name rather than
branching on it, so Parquet becomes one new ``ExportFormat`` entry whose
``serialize`` returns ``bytes`` (``binary=True``) — nothing else in the
request path changes. It isn't implemented today because it would be the
platform's first binary export and its first new runtime dependency
(``pyarrow`` or ``fastparquet``); CSV and JSON cover every consumer that
exists right now (pandas, a spreadsheet, a human).
"""

import csv
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.features.base import FeatureValue
from app.features.dataset import FeatureDataset

#: Rendered for a ``None`` cell in CSV. Empty is the CSV convention for
#: "no value" and is what pandas/R read back as NaN/NA — writing the string
#: "None" or "null" would round-trip as text and quietly poison a column's
#: dtype.
_CSV_NULL = ""


@dataclass(frozen=True, slots=True)
class ExportFormat:
    """One registered export format — everything the service/endpoint need to know.

    ``binary`` tells the endpoint whether ``serialize`` returns ``str``
    (write as text) or ``bytes`` (write as-is) without either caller
    needing to know or guess which formats are text versus binary.
    """

    extension: str
    media_type: str
    binary: bool
    serialize: Callable[[FeatureDataset], str | bytes]


def dataset_filename(dataset: FeatureDataset, extension: str) -> str:
    """A stable, filesystem-safe name identifying what the file holds."""
    symbol = _safe(dataset.symbol)
    timeframe = _safe(dataset.timeframe)
    stamp = dataset.generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{symbol}-{timeframe}-features-{stamp}.{extension}"


def to_csv(dataset: FeatureDataset, *, include_metadata: bool = True) -> str:
    """Serialize as CSV: an optional metadata preamble, then the matrix.

    The preamble is written as ``# key,value`` comment lines rather than as
    a second header block, so the file still loads with a plain
    ``read_csv(..., comment='#')`` in pandas or ``skip`` in R while
    remaining readable to a human. A metadata block that breaks naive
    parsing would just be deleted by the first person who used the file.

    Set ``include_metadata=False`` for a bare matrix, for a consumer that
    cannot skip comment lines at all.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    if include_metadata:
        for key, value in _metadata_pairs(dataset):
            buffer.write(f"# {key},{value}\n")
        for feature_line in _feature_metadata_lines(dataset):
            buffer.write(f"# {feature_line}\n")
        for quality_line in _quality_lines(dataset):
            buffer.write(f"# {quality_line}\n")

    writer.writerow(["timestamp", *(column.name for column in dataset.columns)])
    for timestamp, row in zip(dataset.timestamps, dataset.rows, strict=True):
        writer.writerow([_iso(timestamp), *(_csv_cell(value) for value in row)])

    return buffer.getvalue()


def to_json(dataset: FeatureDataset, *, orient: str = "records") -> str:
    """Serialize as JSON with full provenance.

    ``orient="records"`` (the default) emits one object per row with column
    names as keys — the shape ``pandas.read_json`` and most JS consumers
    expect, and the one that stays correct if columns are reordered.
    ``orient="columns"`` emits parallel arrays instead, which is more
    compact for wide datasets and maps directly onto a numpy array.
    """
    payload: dict[str, Any] = {
        "dataset_id": dataset.dataset_id,
        "symbol": dataset.symbol,
        "timeframe": dataset.timeframe,
        "generated_at": _iso(dataset.generated_at),
        "exported_at": _iso(datetime.now(UTC)),
        "pipeline_version": dataset.pipeline_version,
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
        "meta": {
            "row_count": dataset.row_count,
            "candles_analyzed": dataset.candles_analyzed,
            "rows_dropped": dataset.rows_dropped,
            "warmup_candles": dataset.warmup_candles,
        },
        "quality": {
            "total_rows": dataset.quality.total_rows,
            "rows_returned": dataset.quality.rows_returned,
            "rows_removed": dataset.quality.rows_removed,
            "null_counts": dataset.quality.null_counts,
            "duplicate_timestamps": dataset.quality.duplicate_timestamps,
            "missing_candles": dataset.quality.missing_candles,
            "generation_time_ms": dataset.quality.generation_time_ms,
            "feature_failures": [
                {
                    "feature": failure.feature,
                    "params": failure.params,
                    "error_code": failure.error_code,
                    "error_detail": failure.error_detail,
                }
                for failure in dataset.quality.feature_failures
            ],
        },
    }

    if orient == "columns":
        payload["timestamps"] = [_iso(value) for value in dataset.timestamps]
        payload["data"] = {
            column.name: [row[index] for row in dataset.rows]
            for index, column in enumerate(dataset.columns)
        }
    else:
        payload["data"] = [
            {
                "timestamp": _iso(timestamp),
                **{column.name: row[index] for index, column in enumerate(dataset.columns)},
            }
            for timestamp, row in zip(dataset.timestamps, dataset.rows, strict=True)
        ]

    return json.dumps(payload, indent=2, default=str)


#: Every export format the API accepts, keyed by the wire name
#: (``?format=csv``). Adding a format is one new entry here — see the
#: module docstring for what a future Parquet entry would look like.
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


def _metadata_pairs(dataset: FeatureDataset) -> list[tuple[str, str]]:
    """The provenance lines written above a CSV matrix."""
    return [
        ("dataset_id", dataset.dataset_id),
        ("symbol", dataset.symbol),
        ("timeframe", dataset.timeframe),
        ("generated_at", _iso(dataset.generated_at)),
        ("exported_at", _iso(datetime.now(UTC))),
        ("pipeline_version", dataset.pipeline_version),
        ("rows", str(dataset.row_count)),
        ("candles_analyzed", str(dataset.candles_analyzed)),
        ("rows_dropped", str(dataset.rows_dropped)),
        ("warmup_candles", str(dataset.warmup_candles)),
    ]


def _feature_metadata_lines(dataset: FeatureDataset) -> list[str]:
    """One CSV comment line per requested feature, naming its full provenance."""
    return [
        f"feature.{info.feature},version={info.version} params=({_params_text(info.params)}) "
        f"columns=({','.join(info.columns)}) warmup={info.warmup}"
        for info in dataset.features
    ]


def _quality_lines(dataset: FeatureDataset) -> list[str]:
    """CSV comment lines summarizing the quality report."""
    quality = dataset.quality
    lines = [
        f"quality.duplicate_timestamps,{quality.duplicate_timestamps}",
        f"quality.missing_candles,{quality.missing_candles}",
        f"quality.generation_time_ms,{quality.generation_time_ms:.2f}",
    ]
    for failure in quality.feature_failures:
        lines.append(f"quality.feature_failure,{failure.feature}: {failure.error_detail}")
    return lines


def _params_text(params: dict[str, Any]) -> str:
    """``{"period": 20}`` → ``period=20``, sorted for a stable rendering."""
    return " ".join(f"{key}={params[key]}" for key in sorted(params))


def _csv_cell(value: FeatureValue) -> str | float | int | bool:
    """Render one cell, mapping ``None`` to an empty field."""
    return _CSV_NULL if value is None else value


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal ``Z``, matching every other timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe(value: str) -> str:
    """Strip anything unsafe for a filename."""
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
