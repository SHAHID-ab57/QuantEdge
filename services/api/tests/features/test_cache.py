"""Feature result cache tests — mirrors `tests/unit/indicators/test_cache.py` exactly."""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.base import FeatureColumn, FeatureOutput, FeatureSeries, OHLCVPoint
from app.features.cache import FeatureCache, build_feature_cache_key

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def candles(count: int, *, final_close: float | None = None) -> list[OHLCVPoint]:
    """``count`` hourly candles, optionally overriding the last close."""
    points = [
        OHLCVPoint(
            open_time=BASE + timedelta(hours=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + index,
            volume=10.0,
        )
        for index in range(count)
    ]
    if final_close is not None and points:
        last = points[-1]
        points[-1] = OHLCVPoint(
            open_time=last.open_time,
            open=last.open,
            high=last.high,
            low=last.low,
            close=final_close,
            volume=last.volume,
        )
    return points


def output(value: float) -> FeatureOutput:
    """A one-point output, used as an identifiable cache payload."""
    return FeatureOutput(
        series=[FeatureSeries(column=FeatureColumn(name="x", label="X"), values=[value])]
    )


class TestCacheKey:
    def test_parameter_order_does_not_affect_the_key(self) -> None:
        data = candles(3)
        first = build_feature_cache_key("ohlcv", {"a": 1, "b": 2}, data)
        second = build_feature_cache_key("ohlcv", {"b": 2, "a": 1}, data)
        assert first == second

    def test_different_features_produce_different_keys(self) -> None:
        data = candles(3)
        assert build_feature_cache_key("ohlcv", {}, data) != build_feature_cache_key(
            "candle_shape", {}, data
        )

    def test_different_parameters_produce_different_keys(self) -> None:
        data = candles(3)
        assert build_feature_cache_key("sma", {"period": 5}, data) != build_feature_cache_key(
            "sma", {"period": 6}, data
        )

    def test_different_candle_ranges_produce_different_keys(self) -> None:
        assert build_feature_cache_key("ohlcv", {}, candles(3)) != build_feature_cache_key(
            "ohlcv", {}, candles(4)
        )


class TestCacheBehaviour:
    def test_returns_none_on_a_miss(self) -> None:
        cache = FeatureCache()
        assert cache.get(build_feature_cache_key("ohlcv", {}, candles(3))) is None

    def test_returns_the_stored_value_on_a_hit(self) -> None:
        cache = FeatureCache()
        key = build_feature_cache_key("ohlcv", {}, candles(3))
        cache.put(key, output(1.0))
        assert cache.get(key) is not None

    def test_tracks_hit_and_miss_counters(self) -> None:
        cache = FeatureCache()
        key = build_feature_cache_key("ohlcv", {}, candles(3))
        cache.get(key)
        cache.put(key, output(1.0))
        cache.get(key)
        assert cache.stats == {"hits": 1, "misses": 1, "entries": 1}

    def test_clear_drops_entries_and_resets_counters(self) -> None:
        cache = FeatureCache()
        key = build_feature_cache_key("ohlcv", {}, candles(3))
        cache.put(key, output(1.0))
        cache.get(key)
        cache.clear()
        assert len(cache) == 0
        assert cache.stats == {"hits": 0, "misses": 0, "entries": 0}


class TestEviction:
    def test_never_grows_past_its_bound(self) -> None:
        cache = FeatureCache(max_entries=2)
        for index in range(5):
            cache.put(build_feature_cache_key(f"f{index}", {}, candles(3)), output(float(index)))
        assert len(cache) == 2

    def test_evicts_the_least_recently_used_entry(self) -> None:
        cache = FeatureCache(max_entries=2)
        first = build_feature_cache_key("a", {}, candles(3))
        second = build_feature_cache_key("b", {}, candles(3))
        third = build_feature_cache_key("c", {}, candles(3))
        cache.put(first, output(1.0))
        cache.put(second, output(2.0))
        cache.get(first)  # first is now most-recently-used
        cache.put(third, output(3.0))
        assert cache.get(second) is None  # evicted
        assert cache.get(first) is not None

    def test_rejects_a_non_positive_bound(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            FeatureCache(max_entries=0)
