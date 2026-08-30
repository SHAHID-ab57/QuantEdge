"""Full-dataset column statistics — the backend counterpart of the
frontend's own preview-scoped `column-stats.ts`.

Pure computation over a dataset `FeatureDatasetBuilder.build` already
produced, the same "no second database query" discipline `quality.py` and
`correlation.py` hold themselves to. Field names (`mean`, `std`, `minimum`,
`maximum`) deliberately match `ai_extensions.py`'s `NormalizationStats` —
the two are related concepts (this is a full descriptive report; that is a
normalizer's fit-on-train-split statistics) but are not the same type: this
one additionally reports `count`/`null_count` and covers every column, not
just the ones a future normalizer would fit.
"""

from dataclasses import dataclass, field

from app.features.base import FeatureColumn, FeatureValue


@dataclass(frozen=True, slots=True)
class ColumnStatistics:
    """Summary statistics for one column over the whole (non-preview-capped) dataset.

    `mean`/`std`/`minimum`/`maximum` are `None` for a non-numeric column
    (`dtype` other than `"float"`/`"int"`) — a categorical or boolean
    column's "average" is meaningless, the same gate `correlation.py` and
    the frontend's own `isNumericDtype` already apply.
    """

    column: str
    count: int
    null_count: int
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True, slots=True)
class DatasetStatistics:
    """Per-column statistics for every column in a built dataset."""

    columns: list[ColumnStatistics] = field(default_factory=list)
    row_count: int = 0


def _is_numeric(column: FeatureColumn) -> bool:
    return column.dtype in ("float", "int")


def compute_dataset_statistics(
    columns: list[FeatureColumn], rows: list[list[FeatureValue]]
) -> DatasetStatistics:
    """Compute count/null-count/mean/std/min/max for every column.

    Uses population variance (dividing by `n`, not `n - 1`) — the same
    formula the frontend's own `computeColumnStats` uses, so a value shown
    here and a value the preview table's per-column stats popover shows for
    the same column (when working over the same rows) always agree.
    """
    stats: list[ColumnStatistics] = []
    for index, column in enumerate(columns):
        values = [row[index] for row in rows]
        null_count = sum(1 for value in values if value is None)
        numbers = [float(value) for value in values if isinstance(value, int | float)]

        if not _is_numeric(column) or not numbers:
            stats.append(
                ColumnStatistics(column=column.name, count=len(values), null_count=null_count)
            )
            continue

        mean = sum(numbers) / len(numbers)
        variance = sum((value - mean) ** 2 for value in numbers) / len(numbers)
        stats.append(
            ColumnStatistics(
                column=column.name,
                count=len(values),
                null_count=null_count,
                mean=mean,
                std=variance**0.5,
                minimum=min(numbers),
                maximum=max(numbers),
            )
        )

    return DatasetStatistics(columns=stats, row_count=len(rows))
