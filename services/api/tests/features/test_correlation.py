"""Feature correlation matrix tests — pure computation, no pipeline involved."""

from app.features.base import FeatureColumn
from app.features.correlation import compute_correlation_matrix


def col(name: str, dtype: str = "float") -> FeatureColumn:
    return FeatureColumn(name=name, label=name, dtype=dtype)


class TestCorrelation:
    def test_perfectly_correlated_columns_score_one(self) -> None:
        columns = [col("a"), col("b")]
        rows = [[1.0, 2.0], [2.0, 4.0], [3.0, 6.0], [4.0, 8.0]]
        result = compute_correlation_matrix(columns, rows)
        assert result.columns == ["a", "b"]
        assert result.matrix[0][1] == 1.0
        assert result.matrix[1][0] == 1.0

    def test_perfectly_inversely_correlated_columns_score_negative_one(self) -> None:
        columns = [col("a"), col("b")]
        rows = [[1.0, 8.0], [2.0, 6.0], [3.0, 4.0], [4.0, 2.0]]
        result = compute_correlation_matrix(columns, rows)
        assert result.matrix[0][1] == -1.0

    def test_diagonal_is_always_one(self) -> None:
        columns = [col("a"), col("b"), col("c")]
        rows = [[1.0, 5.0, 9.0], [2.0, 3.0, 1.0], [3.0, 9.0, 4.0]]
        result = compute_correlation_matrix(columns, rows)
        assert all(result.matrix[i][i] == 1.0 for i in range(3))

    def test_a_constant_column_correlates_at_zero_not_nan(self) -> None:
        columns = [col("a"), col("constant")]
        rows = [[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]]
        result = compute_correlation_matrix(columns, rows)
        assert result.matrix[0][1] == 0.0

    def test_excludes_non_numeric_columns(self) -> None:
        columns = [col("a"), col("b"), col("label", dtype="categorical")]
        rows = [[1.0, 2.0, "up"], [2.0, 4.0, "down"], [3.0, 6.0, "up"]]
        result = compute_correlation_matrix(columns, rows)
        assert result.columns == ["a", "b"]

    def test_returns_empty_with_fewer_than_two_numeric_columns(self) -> None:
        columns = [col("a"), col("label", dtype="categorical")]
        rows = [[1.0, "up"], [2.0, "down"]]
        result = compute_correlation_matrix(columns, rows)
        assert result.columns == []
        assert result.matrix == []
        assert result.row_count == 0

    def test_returns_empty_for_zero_columns(self) -> None:
        result = compute_correlation_matrix([], [])
        assert result.columns == []

    def test_skips_null_values_pairwise(self) -> None:
        columns = [col("a"), col("b")]
        rows = [[1.0, 2.0], [None, 4.0], [3.0, None], [4.0, 8.0]]
        result = compute_correlation_matrix(columns, rows)
        # Only rows 0 and 3 have both values present; still a valid (if small) result.
        assert result.row_count == 2
        assert result.matrix[0][1] == 1.0

    def test_row_count_reflects_pairwise_complete_rows_used(self) -> None:
        columns = [col("a"), col("b")]
        rows = [[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]]
        result = compute_correlation_matrix(columns, rows)
        assert result.row_count == 3
