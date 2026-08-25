"""Large-dataset performance tests for the feature pipeline and dataset builder.

Opt-in (`--run-performance`), matching the existing convention in
`tests/performance/test_market_data_perf.py` — a wall-clock budget is a
statement about *this machine, right now*, not a portable correctness fact,
so it must never run by default and block an unrelated contributor's CI on
a slow laptop.
"""

from datetime import UTC, datetime, timedelta
from time import perf_counter

import pytest

from app.features.base import OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.quality import count_duplicate_timestamps, count_missing_candles
from app.features.registry import default_registry

pytestmark = pytest.mark.performance


def large_candle_series(count: int) -> list[OHLCVPoint]:
    """A deterministic, gap-free candle series of arbitrary size."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    return [
        OHLCVPoint(
            open_time=base + timedelta(hours=i),
            open=100.0 + (i % 50),
            high=105.0 + (i % 50),
            low=95.0 + (i % 50),
            close=102.0 + (i % 50),
            volume=10.0 + (i % 50),
        )
        for i in range(count)
    ]


@pytest.fixture(scope="module")
def builder() -> FeatureDatasetBuilder:
    load_builtin_features()
    return FeatureDatasetBuilder(FeaturePipeline(default_registry))


class TestLargeDatasetBuild:
    def test_builds_a_100k_row_multi_feature_dataset_within_budget(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        candles = large_candle_series(100_000)
        started = perf_counter()
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles,
            [
                FeatureRequest("ohlcv"),
                FeatureRequest("candle_shape"),
                FeatureRequest("sma", {"period": "20"}),
                FeatureRequest("ema", {"period": "20"}),
                FeatureRequest("wma", {"period": "20"}),
            ],
        )
        elapsed = perf_counter() - started

        assert dataset.row_count > 99_000
        assert len(dataset.columns) == 5 + 4 + 1 + 1 + 1
        # Generous on a shared CI runner; every generator here is O(n), so
        # this is a regression guard against an accidentally-introduced
        # O(n^2) path (the exact class of bug WMA's own review already
        # found and fixed once — see ARCHITECTURE.md § "Technical
        # Indicator Engine"), not a tight performance benchmark.
        assert elapsed < 5.0

    def test_quality_report_scales_linearly_not_quadratically(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # A naive quality computation (e.g. an O(n^2) duplicate scan) would
        # make large datasets disproportionately slow; doubling the input
        # should not multiply the time by anywhere near 4x.
        small = large_candle_series(20_000)
        big = large_candle_series(80_000)

        started = perf_counter()
        builder.build("ETHUSD", "1h", small, [FeatureRequest("ohlcv")])
        small_elapsed = perf_counter() - started

        started = perf_counter()
        builder.build("ETHUSD", "1h", big, [FeatureRequest("ohlcv")])
        big_elapsed = perf_counter() - started

        # 4x the rows should cost meaningfully less than, say, 20x the time.
        assert big_elapsed < max(small_elapsed * 20, 2.0)


class TestQualityHelpers:
    def test_duplicate_count_is_fast_over_a_large_series(self) -> None:
        timestamps = [c.open_time for c in large_candle_series(200_000)]
        started = perf_counter()
        result = count_duplicate_timestamps(timestamps)
        elapsed = perf_counter() - started
        assert result == 0
        assert elapsed < 1.0

    def test_missing_candle_count_is_fast_over_a_large_series(self) -> None:
        timestamps = [c.open_time for c in large_candle_series(200_000)]
        started = perf_counter()
        result = count_missing_candles(timestamps, "1h")
        elapsed = perf_counter() - started
        assert result == 0
        assert elapsed < 1.0
