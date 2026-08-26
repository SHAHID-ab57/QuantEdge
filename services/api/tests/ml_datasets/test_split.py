"""Chronological splitter tests — no shuffling, no look-ahead bias at the split boundary."""

import pytest

from app.features.ai_extensions import SplitRatios
from app.ml_datasets.errors import InvalidSplitRatiosError
from app.ml_datasets.split import ChronologicalSplitter


def make_feature_dataset(row_count: int):
    """A minimal, valid `FeatureDataset` with `row_count` rows, for split-only tests."""
    from datetime import UTC, datetime, timedelta

    from app.features.base import FeatureColumn
    from app.features.dataset import FeatureDataset
    from app.features.quality import DatasetQualityReport

    base = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [base + timedelta(hours=i) for i in range(row_count)]
    rows = [[float(i)] for i in range(row_count)]
    return FeatureDataset(
        dataset_id="test-dataset",
        symbol="ETHUSD",
        timeframe="1h",
        columns=[FeatureColumn(name="close", label="Close", dtype="float")],
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


class TestChronologicalSplit:
    def test_splits_are_contiguous_and_sum_to_the_whole(self) -> None:
        dataset = make_feature_dataset(100)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.7, validation=0.15, test=0.15)
        )
        assert split.train.row_count + split.validation.row_count + split.test.row_count == 100

    def test_ratios_are_respected(self) -> None:
        dataset = make_feature_dataset(100)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.7, validation=0.15, test=0.15)
        )
        assert split.train.row_count == 70
        assert split.validation.row_count == 15
        assert split.test.row_count == 15

    def test_train_comes_before_validation_comes_before_test_in_time(self) -> None:
        dataset = make_feature_dataset(30)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.5, validation=0.25, test=0.25)
        )
        assert max(split.train.timestamps) < min(split.validation.timestamps)
        assert max(split.validation.timestamps) < min(split.test.timestamps)

    def test_never_reorders_rows_within_a_split(self) -> None:
        dataset = make_feature_dataset(20)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.6, validation=0.2, test=0.2)
        )
        for slice_ in (split.train, split.validation, split.test):
            assert list(slice_.timestamps) == sorted(slice_.timestamps)

    def test_concatenating_all_three_splits_reconstructs_the_original_row_order(self) -> None:
        dataset = make_feature_dataset(17)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.6, validation=0.2, test=0.2)
        )
        reconstructed = [
            *split.train.timestamps,
            *split.validation.timestamps,
            *split.test.timestamps,
        ]
        assert reconstructed == list(dataset.timestamps)

    def test_every_split_keeps_the_parents_dataset_id(self) -> None:
        dataset = make_feature_dataset(10)
        split = ChronologicalSplitter().split(dataset, SplitRatios())
        assert split.train.dataset_id == dataset.dataset_id
        assert split.validation.dataset_id == dataset.dataset_id
        assert split.test.dataset_id == dataset.dataset_id

    def test_quality_rows_returned_reflects_each_slices_own_size(self) -> None:
        dataset = make_feature_dataset(10)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.5, validation=0.3, test=0.2)
        )
        assert split.train.quality.rows_returned == split.train.row_count
        assert split.validation.quality.rows_returned == split.validation.row_count
        assert split.test.quality.rows_returned == split.test.row_count

    def test_a_zero_ratio_split_is_allowed_for_validation_or_test(self) -> None:
        dataset = make_feature_dataset(10)
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=1.0, validation=0.0, test=0.0)
        )
        assert split.train.row_count == 10
        assert split.validation.row_count == 0
        assert split.test.row_count == 0


class TestInvalidRatios:
    def test_rejects_ratios_that_do_not_sum_to_one(self) -> None:
        dataset = make_feature_dataset(10)
        with pytest.raises(InvalidSplitRatiosError):
            ChronologicalSplitter().split(dataset, SplitRatios(train=0.5, validation=0.3, test=0.3))

    def test_rejects_a_negative_ratio(self) -> None:
        dataset = make_feature_dataset(10)
        with pytest.raises(InvalidSplitRatiosError):
            ChronologicalSplitter().split(
                dataset, SplitRatios(train=1.1, validation=-0.1, test=0.0)
            )

    def test_rejects_a_zero_train_ratio(self) -> None:
        dataset = make_feature_dataset(10)
        with pytest.raises(InvalidSplitRatiosError):
            ChronologicalSplitter().split(dataset, SplitRatios(train=0.0, validation=0.5, test=0.5))

    def test_tolerates_floating_point_slack(self) -> None:
        dataset = make_feature_dataset(10)
        # 0.7 + 0.15 + 0.15 is not bit-exact in IEEE 754.
        split = ChronologicalSplitter().split(
            dataset, SplitRatios(train=0.7, validation=0.15, test=0.15)
        )
        assert split.train.row_count == 7
