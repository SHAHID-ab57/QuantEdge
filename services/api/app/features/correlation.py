"""Feature correlation matrix — pairwise Pearson correlation over a built dataset.

Pure computation over data ``FeatureDatasetBuilder.build`` already produced,
the same "no second database query, nothing here recomputes a feature"
discipline ``quality.py`` holds itself to. Scoped to numeric columns only
(``dtype in ("float", "int")``) — a categorical column's "correlation" is
meaningless, the same gate the frontend's own
``column-stats.ts``/``isNumericDtype`` already applies to per-column
statistics.
"""

import math
from dataclasses import dataclass, field

from app.features.base import FeatureColumn, FeatureValue


@dataclass(frozen=True, slots=True)
class FeatureCorrelationMatrix:
    """Pairwise Pearson correlation across every numeric column in a dataset.

    ``matrix[i][j]`` is the correlation between ``columns[i]`` and
    ``columns[j]`` — symmetric by construction, with every diagonal entry
    exactly ``1.0``. Empty (``columns == []``) when fewer than two numeric
    columns are present — a correlation matrix needs at least two variables
    to compare, and this is not an error condition (a single-feature or
    all-categorical dataset is a perfectly valid dataset to have built),
    mirroring how ``RocPrCurveCharts`` on the frontend renders nothing
    rather than raising when its own inputs don't apply.
    """

    columns: list[str] = field(default_factory=list)
    matrix: list[list[float]] = field(default_factory=list)
    #: Rows actually used — pairwise complete rows may be fewer than the
    #: dataset's own row count if `drop_warmup=False` left nulls in play.
    row_count: int = 0


def _is_numeric(column: FeatureColumn) -> bool:
    return column.dtype in ("float", "int")


def compute_correlation_matrix(
    columns: list[FeatureColumn], rows: list[list[FeatureValue]]
) -> FeatureCorrelationMatrix:
    """Compute the pairwise Pearson correlation matrix for a dataset's numeric columns.

    Uses pairwise-complete rows per column pair (skips a row for a given
    pair only if either value in *that pair* is ``None``), rather than
    dropping any row with a null anywhere — the same tolerant-by-default
    posture the rest of this module takes, since a dataset built with
    `drop_warmup=False` may legitimately carry nulls in columns unrelated to
    the pair being compared.
    """
    numeric_indices = [index for index, column in enumerate(columns) if _is_numeric(column)]
    if len(numeric_indices) < 2:
        return FeatureCorrelationMatrix()

    numeric_names = [columns[index].name for index in numeric_indices]
    series = [[row[index] for row in rows] for index in numeric_indices]

    size = len(numeric_indices)
    matrix = [[0.0] * size for _ in range(size)]
    max_pairwise_rows = 0
    for i in range(size):
        matrix[i][i] = 1.0
        for j in range(i + 1, size):
            correlation, pair_rows = _pearson(series[i], series[j])
            matrix[i][j] = correlation
            matrix[j][i] = correlation
            max_pairwise_rows = max(max_pairwise_rows, pair_rows)

    return FeatureCorrelationMatrix(
        columns=numeric_names, matrix=matrix, row_count=max_pairwise_rows
    )


def _pearson(x: list[FeatureValue], y: list[FeatureValue]) -> tuple[float, int]:
    """Pearson correlation coefficient over the pairwise-complete rows of `x`/`y`.

    Returns ``(0.0, 0)`` when fewer than two complete pairs exist or either
    series has zero variance (a constant column has no correlation with
    anything, not an undefined one — `0.0` is the honest answer, never
    ``NaN`` on the wire).
    """
    pairs = [
        (float(a), float(b))
        for a, b in zip(x, y, strict=True)
        if isinstance(a, int | float) and isinstance(b, int | float)
    ]
    if len(pairs) < 2:
        return 0.0, len(pairs)

    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    n = len(pairs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    covariance = sum((a - mean_x) * (b - mean_y) for a, b in pairs)
    variance_x = sum((a - mean_x) ** 2 for a in xs)
    variance_y = sum((b - mean_y) ** 2 for b in ys)
    denominator = math.sqrt(variance_x * variance_y)
    if denominator == 0.0:
        return 0.0, n
    return covariance / denominator, n
