"""Tests for `ColumnNormalizer`/`apply_normalization` — per-column feature
normalization, this platform's first real implementer of
`app.features.ai_extensions.FeatureNormalizer`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.ai_extensions import NormalizationStats
from app.features.base import FeatureColumn, FeatureValue
from app.features.dataset import FeatureDataset
from app.features.quality import DatasetQualityReport
from app.training.normalization import (
    ColumnNormalizer,
    apply_normalization,
    normalization_stats_to_dicts,
)


def make_feature_dataset(columns: dict[str, list[FeatureValue]]) -> FeatureDataset:
    """A minimal, valid `FeatureDataset` with one column per `columns` key.

    Mirrors `tests/ml_datasets/test_split.py`'s own `make_feature_dataset`
    helper, generalized to more than one named column so a normalizer has
    something to fit/transform across.
    """
    row_count = len(next(iter(columns.values())))
    base = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [base + timedelta(hours=i) for i in range(row_count)]
    names = list(columns)
    rows = [[columns[name][i] for name in names] for i in range(row_count)]
    return FeatureDataset(
        dataset_id="test-dataset",
        symbol="ETHUSD",
        timeframe="1h",
        columns=[FeatureColumn(name=name, label=name, dtype="float") for name in names],
        timestamps=timestamps,
        rows=rows,
        features=[],
        candles_analyzed=row_count,
        rows_dropped=0,
        warmup_candles=0,
        pipeline_version="1.0.0",
        generated_at=base,
        quality=DatasetQualityReport(total_rows=row_count, rows_returned=row_count, rows_removed=0),
    )


class TestColumnNormalizerConstruction:
    def test_defaults_to_zscore(self) -> None:
        assert ColumnNormalizer().method == "zscore"

    def test_accepts_minmax(self) -> None:
        assert ColumnNormalizer(method="minmax").method == "minmax"


class TestFit:
    def test_computes_mean_std_min_max_from_the_given_dataset(self) -> None:
        dataset = make_feature_dataset({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})

        stats = ColumnNormalizer().fit(dataset, ["close"])

        assert len(stats) == 1
        assert stats[0].column == "close"
        assert stats[0].mean == pytest.approx(3.0)
        # Population variance: mean((x-3)^2) = (4+1+0+1+4)/5 = 2.0
        assert stats[0].std == pytest.approx(2.0**0.5)
        assert stats[0].minimum == pytest.approx(1.0)
        assert stats[0].maximum == pytest.approx(5.0)

    def test_fits_only_from_the_dataset_it_is_given(self) -> None:
        """The concrete "train-only" proof at the unit level: `fit()` takes exactly
        one `FeatureDataset` argument, so a second, wildly different dataset
        (standing in for validation/test) can never influence the computed stats
        — there is no code path by which it could leak in."""
        train = make_feature_dataset({"close": [10.0, 20.0, 30.0]})
        # A hypothetical validation/test set with an extreme outlier that would
        # shift the mean/std enormously if it were ever consulted.
        make_feature_dataset({"close": [-1_000_000.0, 1_000_000.0]})

        stats = ColumnNormalizer().fit(train, ["close"])

        assert stats[0].mean == pytest.approx(20.0)
        assert stats[0].minimum == pytest.approx(10.0)
        assert stats[0].maximum == pytest.approx(30.0)

    def test_fits_each_column_independently(self) -> None:
        dataset = make_feature_dataset(
            {"close": [1000.0, 2000.0, 3000.0], "candle_body": [1.0, 2.0, 3.0]}
        )

        stats = ColumnNormalizer().fit(dataset, ["close", "candle_body"])

        by_name = {entry.column: entry for entry in stats}
        assert by_name["close"].mean == pytest.approx(2000.0)
        assert by_name["candle_body"].mean == pytest.approx(2.0)

    def test_reports_none_statistics_for_a_column_with_no_numeric_values(self) -> None:
        dataset = make_feature_dataset({"broken": [None, None, None]})

        stats = ColumnNormalizer().fit(dataset, ["broken"])

        assert stats[0].mean is None
        assert stats[0].std is None


class TestTransform:
    def test_zscore_output_has_zero_mean_and_unit_std_on_the_fitted_dataset(self) -> None:
        dataset = make_feature_dataset({"close": [1000.0, 2000.0, 3000.0, 4000.0, 5000.0]})
        normalizer = ColumnNormalizer(method="zscore")
        stats = normalizer.fit(dataset, ["close"])

        transformed = normalizer.transform(dataset, stats)

        values = [float(row[0]) for row in transformed.rows]  # type: ignore[arg-type]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        assert mean == pytest.approx(0.0, abs=1e-9)
        assert variance**0.5 == pytest.approx(1.0)

    def test_zscore_constant_column_returns_zero_not_nan_or_a_division_error(self) -> None:
        dataset = make_feature_dataset({"flat": [5.0, 5.0, 5.0]})
        normalizer = ColumnNormalizer(method="zscore")
        stats = normalizer.fit(dataset, ["flat"])
        assert stats[0].std == 0.0

        transformed = normalizer.transform(dataset, stats)

        assert [row[0] for row in transformed.rows] == [0.0, 0.0, 0.0]

    def test_minmax_bounds_land_in_zero_one(self) -> None:
        dataset = make_feature_dataset({"close": [1000.0, 1500.0, 2000.0]})
        normalizer = ColumnNormalizer(method="minmax")
        stats = normalizer.fit(dataset, ["close"])

        transformed = normalizer.transform(dataset, stats)

        values = [row[0] for row in transformed.rows]
        assert values[0] == pytest.approx(0.0)
        assert values[1] == pytest.approx(0.5)
        assert values[2] == pytest.approx(1.0)

    def test_minmax_constant_column_returns_zero(self) -> None:
        dataset = make_feature_dataset({"flat": [5.0, 5.0]})
        normalizer = ColumnNormalizer(method="minmax")
        stats = normalizer.fit(dataset, ["flat"])

        transformed = normalizer.transform(dataset, stats)

        assert [row[0] for row in transformed.rows] == [0.0, 0.0]

    def test_ignores_a_stats_entry_not_present_in_the_dataset(self) -> None:
        dataset = make_feature_dataset({"close": [1.0, 2.0]})
        normalizer = ColumnNormalizer()
        phantom = NormalizationStats(column="does_not_exist", mean=0.0, std=1.0)

        transformed = normalizer.transform(dataset, [phantom])

        # Untouched — the phantom column was simply skipped.
        assert transformed.rows == [[1.0], [2.0]]

    def test_leaves_non_numeric_cells_untouched(self) -> None:
        dataset = make_feature_dataset({"direction": ["up", "down"]})
        normalizer = ColumnNormalizer()
        stats = [NormalizationStats(column="direction", mean=0.0, std=1.0)]

        transformed = normalizer.transform(dataset, stats)

        assert transformed.rows == [["up"], ["down"]]

    def test_applies_train_fitted_stats_to_a_different_dataset_unchanged(self) -> None:
        """The other half of the "fit on train, apply to validation/test" contract:
        `transform()` never re-fits — it only ever applies the stats it is handed."""
        train = make_feature_dataset({"close": [10.0, 20.0, 30.0]})
        validation = make_feature_dataset({"close": [15.0]})
        normalizer = ColumnNormalizer()
        stats = normalizer.fit(train, ["close"])  # mean=20, std=~8.165

        transformed = normalizer.transform(validation, stats)

        assert stats[0].std is not None
        expected = (15.0 - 20.0) / stats[0].std
        assert transformed.rows[0][0] == pytest.approx(expected)


class TestApplyNormalization:
    def test_matches_columnnormalizer_transform_over_equivalent_data(self) -> None:
        dataset = make_feature_dataset({"close": [1000.0, 2000.0, 3000.0]})
        normalizer = ColumnNormalizer()
        stats = normalizer.fit(dataset, ["close"])
        transformed = normalizer.transform(dataset, stats)

        raw_rows = [[1000.0], [2000.0], [3000.0]]
        result = apply_normalization(raw_rows, stats)

        assert result == [row for row in transformed.rows]

    def test_defaults_to_zscore(self) -> None:
        stats = [NormalizationStats(column="x", mean=10.0, std=2.0)]

        result = apply_normalization([[12.0], [8.0]], stats)

        assert result == [[1.0], [-1.0]]

    def test_supports_minmax(self) -> None:
        stats = [NormalizationStats(column="x", minimum=0.0, maximum=10.0)]

        result = apply_normalization([[5.0]], stats, method="minmax")

        assert result == [[0.5]]


class TestNormalizationStatsToDicts:
    def test_none_passes_through(self) -> None:
        assert normalization_stats_to_dicts(None) is None

    def test_converts_each_entry_to_a_plain_dict(self) -> None:
        stats = [
            NormalizationStats(column="close", mean=100.0, std=5.0, minimum=90.0, maximum=110.0)
        ]

        result = normalization_stats_to_dicts(stats)

        assert result == [
            {"column": "close", "mean": 100.0, "std": 5.0, "minimum": 90.0, "maximum": 110.0}
        ]
        # Round-trips back into a real `NormalizationStats`, the same shape
        # `TrainingJobService._normalize_prediction_rows` reconstructs from.
        assert NormalizationStats(**result[0]) == stats[0]  # type: ignore[arg-type]
