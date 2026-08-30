"""Dataset statistics tests — pure computation, no pipeline involved."""

import math

from app.features.base import FeatureColumn
from app.features.statistics import compute_dataset_statistics


def col(name: str, dtype: str = "float") -> FeatureColumn:
    return FeatureColumn(name=name, label=name, dtype=dtype)


class TestStatistics:
    def test_computes_exact_mean_min_max_for_known_values(self) -> None:
        columns = [col("a")]
        rows = [[1.0], [2.0], [3.0], [4.0]]
        result = compute_dataset_statistics(columns, rows)
        stats = result.columns[0]
        assert stats.mean == 2.5
        assert stats.minimum == 1.0
        assert stats.maximum == 4.0
        assert stats.count == 4
        assert stats.null_count == 0

    def test_computes_population_standard_deviation(self) -> None:
        # Population variance of [2, 4, 4, 4, 5, 5, 7, 9] is 4, std is 2 —
        # a textbook example, and the same population (not sample) formula
        # the frontend's own computeColumnStats uses.
        columns = [col("a")]
        rows = [[2.0], [4.0], [4.0], [4.0], [5.0], [5.0], [7.0], [9.0]]
        result = compute_dataset_statistics(columns, rows)
        assert math.isclose(result.columns[0].std, 2.0, rel_tol=1e-9)

    def test_counts_nulls_separately_from_the_numeric_stats(self) -> None:
        columns = [col("a")]
        rows = [[1.0], [None], [3.0], [None]]
        result = compute_dataset_statistics(columns, rows)
        stats = result.columns[0]
        assert stats.count == 4
        assert stats.null_count == 2
        assert stats.mean == 2.0

    def test_non_numeric_columns_get_count_and_nulls_only(self) -> None:
        columns = [col("label", dtype="categorical")]
        rows = [["up"], ["down"], [None]]
        result = compute_dataset_statistics(columns, rows)
        stats = result.columns[0]
        assert stats.count == 3
        assert stats.null_count == 1
        assert stats.mean is None
        assert stats.std is None
        assert stats.minimum is None
        assert stats.maximum is None

    def test_an_entirely_null_numeric_column_reports_none_rather_than_raising(self) -> None:
        columns = [col("a")]
        rows = [[None], [None]]
        result = compute_dataset_statistics(columns, rows)
        stats = result.columns[0]
        assert stats.count == 2
        assert stats.null_count == 2
        assert stats.mean is None

    def test_row_count_matches_the_dataset(self) -> None:
        columns = [col("a")]
        rows = [[1.0], [2.0], [3.0]]
        result = compute_dataset_statistics(columns, rows)
        assert result.row_count == 3

    def test_covers_every_column_independently(self) -> None:
        columns = [col("a"), col("b", dtype="categorical")]
        rows = [[1.0, "x"], [2.0, "y"]]
        result = compute_dataset_statistics(columns, rows)
        assert len(result.columns) == 2
        assert result.columns[0].mean == 1.5
        assert result.columns[1].mean is None
