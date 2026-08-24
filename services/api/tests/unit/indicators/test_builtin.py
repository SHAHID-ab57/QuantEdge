"""Built-in indicator tests.

Two distinct concerns:

- **Discovery** — that dropping a module into ``app/indicators/builtin/``
  is all it takes for an indicator to become available, which is the
  architectural promise the whole design rests on.
- **Correctness** — each reference indicator against hand-computed values,
  so a refactor of the engine can never quietly change what the numbers
  mean.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.indicators.base import OHLCVPoint
from app.indicators.builtin import load_builtin_indicators
from app.indicators.engine import IndicatorEngine
from app.indicators.registry import default_registry

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def series_from(closes: list[float]) -> list[OHLCVPoint]:
    """Hourly candles whose OHLC all track ``closes`` (volume held constant)."""
    return [
        OHLCVPoint(
            open_time=BASE + timedelta(hours=index),
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=100.0,
        )
        for index, close in enumerate(closes)
    ]


@pytest.fixture(scope="module")
def engine() -> IndicatorEngine:
    """An engine over the real, auto-discovered builtin registry."""
    load_builtin_indicators()
    return IndicatorEngine(default_registry)


class TestDiscovery:
    def test_loads_every_builtin_indicator(self, engine: IndicatorEngine) -> None:
        assert set(engine.registry.names()) >= {"sma", "ema", "wma", "rsi"}

    def test_is_idempotent(self, engine: IndicatorEngine) -> None:
        # Any entry point may call it defensively; a second call must not
        # raise DuplicateIndicatorError.
        before = len(engine.registry)
        load_builtin_indicators()
        assert len(engine.registry) == before

    def test_every_builtin_publishes_parameters_and_outputs(self, engine: IndicatorEngine) -> None:
        # A UI builds its form from this metadata, so an indicator that
        # declared none would render an empty, unusable form.
        for metadata in engine.describe_all():
            assert metadata.outputs, f"{metadata.name} declares no output series"
            assert metadata.label and metadata.description
            assert metadata.category

    def test_every_builtin_declares_a_price_source_choice(self, engine: IndicatorEngine) -> None:
        for metadata in engine.describe_all():
            source = next(spec for spec in metadata.parameters if spec.name == "source")
            assert source.choices == ("open", "high", "low", "close")

    def test_every_builtin_publishes_complete_engineering_metadata(
        self, engine: IndicatorEngine
    ) -> None:
        # version/author/complexity/warmup_description are additive fields
        # (see IndicatorMetadata) — every shipped indicator sets them
        # explicitly rather than relying on the generic dataclass default,
        # so the frontend's metadata card never has to show a placeholder
        # for a built-in indicator.
        for metadata in engine.describe_all():
            assert metadata.version, f"{metadata.name} declares no version"
            assert metadata.author, f"{metadata.name} declares no author"
            assert metadata.complexity != "Not documented", (
                f"{metadata.name} left complexity at the generic default"
            )
            assert metadata.warmup_description, f"{metadata.name} declares no warmup_description"

    def test_rejects_an_unsupported_price_source(self, engine: IndicatorEngine) -> None:
        from app.indicators.errors import InvalidIndicatorParameterError

        for name in ("sma", "ema", "wma", "rsi"):
            with pytest.raises(InvalidIndicatorParameterError, match="must be one of"):
                engine.run(name, series_from([1, 2, 3, 4, 5]), {"source": "vwap"})


class TestSimpleMovingAverage:
    def test_matches_a_hand_computed_average(self, engine: IndicatorEngine) -> None:
        run = engine.run("sma", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        # (1+2+3)/3, (2+3+4)/3, (3+4+5)/3
        assert run.output.series[0].values == [None, None, 2.0, 3.0, 4.0]

    def test_leaves_the_warmup_period_null(self, engine: IndicatorEngine) -> None:
        run = engine.run("sma", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        assert run.output.series[0].values[:2] == [None, None]
        assert run.warmup == 3

    def test_a_period_of_one_reproduces_the_source_series(self, engine: IndicatorEngine) -> None:
        run = engine.run("sma", series_from([7, 8, 9]), {"period": "1"})
        assert run.output.series[0].values == [7.0, 8.0, 9.0]

    def test_honours_the_source_parameter(self, engine: IndicatorEngine) -> None:
        # `high` is close + 1 in this fixture, so every point shifts by one.
        run = engine.run("sma", series_from([1, 2, 3]), {"period": "3", "source": "high"})
        assert run.output.series[0].values[-1] == pytest.approx(3.0)

    def test_labels_the_series_with_its_period(self, engine: IndicatorEngine) -> None:
        run = engine.run("sma", series_from([1, 2, 3]), {"period": "3"})
        assert run.output.series[0].label == "SMA(3)"


class TestExponentialMovingAverage:
    def test_seeds_from_the_first_simple_average(self, engine: IndicatorEngine) -> None:
        run = engine.run("ema", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        # Seed at index 2 is the SMA of [1,2,3].
        assert run.output.series[0].values[2] == pytest.approx(2.0)

    def test_applies_the_standard_recurrence_after_the_seed(self, engine: IndicatorEngine) -> None:
        run = engine.run("ema", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        # multiplier = 2/(3+1) = 0.5; (4-2)*0.5+2 = 3, then (5-3)*0.5+3 = 4.
        assert run.output.series[0].values[3] == pytest.approx(3.0)
        assert run.output.series[0].values[4] == pytest.approx(4.0)

    def test_leaves_the_warmup_period_null(self, engine: IndicatorEngine) -> None:
        run = engine.run("ema", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        assert run.output.series[0].values[:2] == [None, None]

    def test_reacts_faster_than_an_sma_of_the_same_period(self, engine: IndicatorEngine) -> None:
        # The defining property worth pinning: after a jump, the EMA is
        # closer to the new level than the equivalent SMA.
        closes = [10.0] * 10 + [20.0] * 3
        data = series_from(closes)
        ema = engine.run("ema", data, {"period": "10"}).output.series[0].values[-1]
        sma = engine.run("sma", data, {"period": "10"}).output.series[0].values[-1]
        assert ema is not None and sma is not None
        assert ema > sma


class TestWeightedMovingAverage:
    def test_matches_a_hand_computed_average(self, engine: IndicatorEngine) -> None:
        run = engine.run("wma", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        # weights 1,2,3: (1*1+2*2+3*3)/6, (2*1+3*2+4*3)/6, (3*1+4*2+5*3)/6
        assert run.output.series[0].values == [
            None,
            None,
            pytest.approx(14 / 6),
            pytest.approx(20 / 6),
            pytest.approx(26 / 6),
        ]

    def test_leaves_the_warmup_period_null(self, engine: IndicatorEngine) -> None:
        run = engine.run("wma", series_from([1, 2, 3, 4, 5]), {"period": "3"})
        assert run.output.series[0].values[:2] == [None, None]
        assert run.warmup == 3

    def test_a_period_of_one_reproduces_the_source_series(self, engine: IndicatorEngine) -> None:
        run = engine.run("wma", series_from([7, 8, 9]), {"period": "1"})
        assert run.output.series[0].values == [7.0, 8.0, 9.0]

    def test_honours_the_source_parameter(self, engine: IndicatorEngine) -> None:
        # `high` is close + 1 in this fixture, so every point shifts by one:
        # WMA(1,2,3) with weights 1,2,3 is 14/6, so WMA(2,3,4) is 20/6.
        run = engine.run("wma", series_from([1, 2, 3]), {"period": "3", "source": "high"})
        assert run.output.series[0].values[-1] == pytest.approx(20 / 6)

    def test_labels_the_series_with_its_period(self, engine: IndicatorEngine) -> None:
        run = engine.run("wma", series_from([1, 2, 3]), {"period": "3"})
        assert run.output.series[0].label == "WMA(3)"

    def test_reacts_at_least_as_fast_as_an_sma_of_the_same_period(
        self, engine: IndicatorEngine
    ) -> None:
        # The defining property: after an up-jump, weighting recent candles
        # more heavily pulls the WMA at least as close to the new level as
        # the equivalent SMA.
        closes = [10.0] * 10 + [20.0] * 3
        data = series_from(closes)
        wma = engine.run("wma", data, {"period": "10"}).output.series[0].values[-1]
        sma = engine.run("sma", data, {"period": "10"}).output.series[0].values[-1]
        assert wma is not None and sma is not None
        assert wma > sma

    def test_holds_steady_at_a_constant_price(self, engine: IndicatorEngine) -> None:
        # Every weighted combination of the same value is that value,
        # regardless of period — a basic sanity check on the weighting math.
        run = engine.run("wma", series_from([5.0] * 10), {"period": "4"})
        computed = [value for value in run.output.series[0].values if value is not None]
        assert computed
        assert all(value == pytest.approx(5.0) for value in computed)

    def test_raises_insufficient_data_for_an_empty_range(self, engine: IndicatorEngine) -> None:
        from app.indicators.errors import InsufficientDataError

        with pytest.raises(InsufficientDataError) as exc_info:
            engine.run("wma", series_from([]), {"period": "3"})
        assert exc_info.value.required == 3
        assert exc_info.value.available == 0

    def test_rejects_a_zero_period(self, engine: IndicatorEngine) -> None:
        from app.indicators.errors import InvalidIndicatorParameterError

        with pytest.raises(InvalidIndicatorParameterError, match="must be >= 1"):
            engine.run("wma", series_from([1, 2, 3]), {"period": "0"})

    def test_rejects_a_negative_period(self, engine: IndicatorEngine) -> None:
        from app.indicators.errors import InvalidIndicatorParameterError

        with pytest.raises(InvalidIndicatorParameterError, match="must be >= 1"):
            engine.run("wma", series_from([1, 2, 3]), {"period": "-5"})

    def test_matches_an_independent_reference_implementation_on_a_large_dataset(
        self, engine: IndicatorEngine
    ) -> None:
        # 5,000 candles is well beyond anything a research request would
        # realistically load, chosen to exercise the O(n * period) rolling
        # computation without timing out, cross-checked against a naive
        # from-scratch weighted average at several points rather than just
        # asserting "it didn't crash".
        closes = [100.0 + (index % 37) * 0.75 for index in range(5_000)]
        period = 50
        run = engine.run("wma", series_from(closes), {"period": str(period)})
        values = run.output.series[0].values
        assert len(values) == 5_000
        assert values[period - 2] is None
        assert values[period - 1] is not None

        weight_sum = period * (period + 1) / 2.0
        for index in (period - 1, 500, 2_500, 4_999):
            window = closes[index - period + 1 : index + 1]
            expected = sum((pos + 1) * value for pos, value in enumerate(window)) / weight_sum
            assert values[index] == pytest.approx(expected)


class TestRelativeStrengthIndex:
    def test_is_one_hundred_when_every_change_is_a_gain(self, engine: IndicatorEngine) -> None:
        run = engine.run("rsi", series_from([float(i) for i in range(1, 20)]), {"period": "14"})
        assert run.output.series[0].values[-1] == pytest.approx(100.0)

    def test_is_zero_when_every_change_is_a_loss(self, engine: IndicatorEngine) -> None:
        run = engine.run("rsi", series_from([float(i) for i in range(20, 1, -1)]), {"period": "14"})
        assert run.output.series[0].values[-1] == pytest.approx(0.0)

    def test_the_seed_is_exactly_fifty_when_gains_and_losses_balance(
        self, engine: IndicatorEngine
    ) -> None:
        # Alternating +1/-1 puts 7 gains and 7 losses in the 14-change seed
        # window, so the seeded value (at index 14) is exactly 50.
        closes = [10.0 + (1.0 if index % 2 else 0.0) for index in range(30)]
        run = engine.run("rsi", series_from(closes), {"period": "14"})
        assert run.output.series[0].values[14] == pytest.approx(50.0, abs=1e-9)

    def test_smoothing_leans_toward_the_most_recent_change(self, engine: IndicatorEngine) -> None:
        # Past the seed, Wilder smoothing weights the newest change, so an
        # otherwise perfectly balanced series still reads above 50 after an
        # up-tick and below 50 after a down-tick. Pinning this stops a
        # future "simplification" to a plain mean from going unnoticed.
        balanced = [10.0 + (1.0 if index % 2 else 0.0) for index in range(30)]
        after_up_tick = engine.run("rsi", series_from(balanced), {"period": "14"})
        after_down_tick = engine.run("rsi", series_from(balanced[:-1]), {"period": "14"})

        assert after_up_tick.output.series[0].values[-1] > 50.0
        assert after_down_tick.output.series[0].values[-1] < 50.0

    def test_warmup_is_one_longer_than_the_period(self, engine: IndicatorEngine) -> None:
        # The first candle yields no change, so RSI needs period + 1 candles.
        run = engine.run("rsi", series_from([float(i) for i in range(1, 20)]), {"period": "14"})
        assert run.warmup == 15
        assert run.output.series[0].values[13] is None
        assert run.output.series[0].values[14] is not None

    def test_stays_within_zero_and_one_hundred(self, engine: IndicatorEngine) -> None:
        closes = [10, 12, 11, 15, 14, 18, 17, 13, 19, 20, 16, 22, 21, 25, 24, 28, 30, 27]
        run = engine.run("rsi", series_from([float(c) for c in closes]), {"period": "5"})
        computed = [value for value in run.output.series[0].values if value is not None]
        assert computed
        assert all(0.0 <= value <= 100.0 for value in computed)

    def test_rejects_a_period_below_two(self, engine: IndicatorEngine) -> None:
        from app.indicators.errors import InvalidIndicatorParameterError

        with pytest.raises(InvalidIndicatorParameterError, match="must be >= 2"):
            engine.run("rsi", series_from([1, 2, 3]), {"period": "1"})


class TestLargeDatasets:
    """SMA and EMA against independent, from-scratch reference computations
    at scale — WMA already has its own equivalent test
    (``test_matches_an_independent_reference_implementation_on_a_large_dataset``).
    """

    def test_sma_matches_a_naive_average_at_scale(self, engine: IndicatorEngine) -> None:
        closes = [100.0 + (index % 41) * 0.6 for index in range(5_000)]
        period = 50
        run = engine.run("sma", series_from(closes), {"period": str(period)})
        values = run.output.series[0].values
        assert len(values) == 5_000
        for index in (period - 1, 500, 2_500, 4_999):
            window = closes[index - period + 1 : index + 1]
            assert values[index] == pytest.approx(sum(window) / period)

    def test_ema_stays_finite_and_bounded_at_scale(self, engine: IndicatorEngine) -> None:
        # EMA's recursion is the one place floating-point drift could in
        # principle compound; over 5,000 points it must still land well
        # inside the range the input data itself spans — never NaN, never
        # diverging.
        closes = [100.0 + (index % 41) * 0.6 for index in range(5_000)]
        run = engine.run("ema", series_from(closes), {"period": "50"})
        computed = [value for value in run.output.series[0].values if value is not None]
        assert len(computed) == 5_000 - 49
        assert all(value == value for value in computed)  # not NaN
        assert all(min(closes) - 1 <= value <= max(closes) + 1 for value in computed)


class TestRepeatedCalculationIsDeterministic:
    """Every trend indicator must return bit-for-bit identical output for
    bit-for-bit identical input, run twice.

    Not a tautology: it would catch a bug where an indicator reads from
    mutable shared state, iterates a ``set``/``dict`` in an order Python
    doesn't guarantee, or depends on wall-clock time — none of which are
    true today, but any of which a future refactor (or a future indicator
    copying an unwary pattern) could introduce silently. A caching engine
    in particular makes this worth pinning explicitly: a cache bug that
    mutated a cached array in place would only show up on the *second*
    read of the same key, which is exactly what this test exercises.
    """

    @staticmethod
    def _run_twice(engine: IndicatorEngine, name: str, params: dict[str, str]):  # noqa: ANN205
        closes = [100.0 + (index % 17) * 0.37 - (index % 5) * 1.13 for index in range(300)]
        candles = series_from(closes)
        first = engine.run(name, candles, params)
        second = engine.run(name, candles, params)
        return first, second

    def test_sma_is_deterministic(self, engine: IndicatorEngine) -> None:
        first, second = self._run_twice(engine, "sma", {"period": "20"})
        assert first.output.series[0].values == second.output.series[0].values

    def test_ema_is_deterministic(self, engine: IndicatorEngine) -> None:
        first, second = self._run_twice(engine, "ema", {"period": "20"})
        assert first.output.series[0].values == second.output.series[0].values

    def test_wma_is_deterministic(self, engine: IndicatorEngine) -> None:
        first, second = self._run_twice(engine, "wma", {"period": "20"})
        assert first.output.series[0].values == second.output.series[0].values

    def test_rsi_is_deterministic(self, engine: IndicatorEngine) -> None:
        first, second = self._run_twice(engine, "rsi", {"period": "14"})
        assert first.output.series[0].values == second.output.series[0].values

    def test_wma_is_deterministic_through_the_result_cache(self) -> None:
        # A cache hit must return the identical values a fresh calculation
        # would — the whole point of caching is that it's invisible to the
        # caller, including in floating-point terms.
        from app.indicators.cache import IndicatorCache

        cached_engine = IndicatorEngine(default_registry, IndicatorCache())
        candles = series_from([100.0 + (index % 13) * 0.5 for index in range(200)])
        miss = cached_engine.run("wma", candles, {"period": "20"})
        hit = cached_engine.run("wma", candles, {"period": "20"})
        assert miss.cache_status == "miss"
        assert hit.cache_status == "hit"
        assert miss.output.series[0].values == hit.output.series[0].values
