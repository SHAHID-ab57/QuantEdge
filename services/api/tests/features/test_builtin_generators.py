"""Built-in feature generator tests — the maths and the discovery contract.

Each generator is exercised independently through the pipeline, so a
generator is testable in isolation exactly as the brief requires while
still going through the alignment/validation guarantees it will have in
production.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.base import OHLCVPoint
from app.features.builtin import INDICATOR_BACKED_FEATURES, load_builtin_features
from app.features.builtin.indicator_feature import IndicatorFeature, _column_suffix
from app.features.errors import InvalidFeatureParameterError
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry
from app.indicators.builtin import load_builtin_indicators
from app.indicators.engine import IndicatorEngine
from app.indicators.registry import default_registry as default_indicator_registry


@pytest.fixture(scope="module")
def pipeline() -> FeaturePipeline:
    """The application's real feature catalogue."""
    load_builtin_features()
    return FeaturePipeline(default_registry)


def candle(
    hour: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
) -> OHLCVPoint:
    return OHLCVPoint(
        open_time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def columns_of(output) -> dict[str, list]:  # noqa: ANN001 - test helper over FeatureOutput
    """Map a generator's output to ``{column name: values}`` for assertions."""
    return {series.column.name: series.values for series in output.series}


class TestDiscovery:
    def test_every_required_generator_is_registered(self, pipeline: FeaturePipeline) -> None:
        names = {entry.name for entry in pipeline.describe_all()}
        assert {"ohlcv", "sma", "ema", "wma", "candle_shape"} <= names

    def test_builtin_discovery_needs_no_explicit_import(self) -> None:
        # Adding a hand-written generator means adding one file — no
        # registry edit, no import to remember. This pins that.
        registry = default_registry
        load_builtin_features()
        assert registry.has("ohlcv")
        assert registry.has("candle_shape")

    def test_loading_is_idempotent(self) -> None:
        before = len(default_registry)
        load_builtin_features()
        load_builtin_features()
        assert len(default_registry) == before

    def test_every_generator_publishes_engineering_metadata(
        self, pipeline: FeaturePipeline
    ) -> None:
        for entry in pipeline.describe_all():
            assert entry.version
            assert entry.author
            assert entry.complexity
            assert entry.label
            assert entry.category


class TestOhlcv:
    def test_projects_all_five_raw_fields(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("ohlcv", [candle(0, open_=10, high=12, low=9, close=11, volume=100)])
        values = columns_of(run.output)
        assert values == {
            "open": [10.0],
            "high": [12.0],
            "low": [9.0],
            "close": [11.0],
            "volume": [100.0],
        }

    def test_needs_no_warmup(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.warmup_for("ohlcv") == 0

    def test_accepts_no_parameters(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(InvalidFeatureParameterError):
            pipeline.run("ohlcv", [candle(0, open_=1, high=2, low=1, close=2)], {"period": "5"})


class TestCandleShape:
    def test_decomposes_an_up_candle(self, pipeline: FeaturePipeline) -> None:
        # open 10, close 14, high 16, low 8 → body 4, upper 2, lower 2.
        run = pipeline.run("candle_shape", [candle(0, open_=10, high=16, low=8, close=14)])
        values = columns_of(run.output)
        assert values["candle_body"] == [4.0]
        assert values["upper_wick"] == [2.0]
        assert values["lower_wick"] == [2.0]
        assert values["candle_direction"] == ["up"]

    def test_decomposes_a_down_candle(self, pipeline: FeaturePipeline) -> None:
        # open 14, close 10 → body 4, upper = 16-14 = 2, lower = 10-8 = 2.
        run = pipeline.run("candle_shape", [candle(0, open_=14, high=16, low=8, close=10)])
        values = columns_of(run.output)
        assert values["candle_body"] == [4.0]
        assert values["upper_wick"] == [2.0]
        assert values["lower_wick"] == [2.0]
        assert values["candle_direction"] == ["down"]

    def test_reports_a_doji_as_flat_with_a_zero_body(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("candle_shape", [candle(0, open_=10, high=12, low=8, close=10)])
        values = columns_of(run.output)
        assert values["candle_body"] == [0.0]
        assert values["candle_direction"] == ["flat"]

    def test_body_and_wicks_span_the_full_high_low_range(self, pipeline: FeaturePipeline) -> None:
        # The invariant that justifies computing all four in one pass.
        bar = candle(0, open_=10, high=16, low=8, close=14)
        run = pipeline.run("candle_shape", [bar])
        values = columns_of(run.output)
        total = values["candle_body"][0] + values["upper_wick"][0] + values["lower_wick"][0]
        assert total == pytest.approx(bar.high - bar.low)

    def test_normalizes_to_fractions_of_the_range(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run(
            "candle_shape",
            [candle(0, open_=10, high=16, low=8, close=14)],
            {"normalize": "true"},
        )
        values = columns_of(run.output)
        assert values["candle_body"] == [pytest.approx(0.5)]  # 4 / 8
        assert values["upper_wick"] == [pytest.approx(0.25)]
        assert values["lower_wick"] == [pytest.approx(0.25)]

    def test_normalized_fractions_sum_to_one(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run(
            "candle_shape",
            [candle(0, open_=11, high=20, low=3, close=17)],
            {"normalize": "true"},
        )
        values = columns_of(run.output)
        total = values["candle_body"][0] + values["upper_wick"][0] + values["lower_wick"][0]
        assert total == pytest.approx(1.0)

    def test_reports_a_flat_candles_fractions_as_undefined_not_zero(
        self, pipeline: FeaturePipeline
    ) -> None:
        # A candle with no range has no fraction to report. Dividing by zero
        # or inventing a 0 would both be worse than saying "undefined".
        run = pipeline.run(
            "candle_shape",
            [candle(0, open_=10, high=10, low=10, close=10)],
            {"normalize": "true"},
        )
        values = columns_of(run.output)
        assert values["candle_body"] == [None]
        assert values["upper_wick"] == [None]
        assert values["lower_wick"] == [None]
        assert values["candle_direction"] == ["flat"]  # direction is still defined

    def test_does_not_normalize_by_default(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("candle_shape", [candle(0, open_=10, high=16, low=8, close=14)])
        assert columns_of(run.output)["candle_body"] == [4.0]

    def test_direction_is_declared_categorical(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("candle_shape", [candle(0, open_=10, high=16, low=8, close=14)])
        by_name = {s.column.name: s.column for s in run.output.series}
        assert by_name["candle_direction"].dtype == "categorical"
        assert by_name["candle_body"].dtype == "float"

    def test_needs_no_warmup(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.warmup_for("candle_shape") == 0


class TestRealizedVolatility:
    """MODEL-QUALITY-T2: population stdev of trailing hourly log returns."""

    def test_registered_and_discoverable(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.registry.has("realized_volatility")

    def test_matches_a_direct_pstdev_computation(self, pipeline: FeaturePipeline) -> None:
        import math
        from statistics import pstdev

        closes = [100.0, 101.0, 100.0, 103.0, 100.0]
        bars = [candle(i, open_=c, high=c, low=c, close=c) for i, c in enumerate(closes)]
        run = pipeline.run("realized_volatility", bars, {"window": "2"})
        values = columns_of(run.output)["realized_volatility_2"]

        log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        assert values[0] is None
        assert values[1] is None
        assert values[2] == pytest.approx(pstdev(log_returns[0:2]))
        assert values[3] == pytest.approx(pstdev(log_returns[1:3]))
        assert values[4] == pytest.approx(pstdev(log_returns[2:4]))

    def test_warmup_equals_the_window(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.warmup_for("realized_volatility", {"window": "24"}) == 24
        assert pipeline.warmup_for("realized_volatility") == 24  # default

    def test_column_name_encodes_the_window(self, pipeline: FeaturePipeline) -> None:
        bars = [candle(i, open_=100 + i, high=101 + i, low=99 + i, close=100 + i) for i in range(6)]
        run = pipeline.run("realized_volatility", bars, {"window": "3"})
        assert list(columns_of(run.output).keys()) == ["realized_volatility_3"]

    def test_never_raises_on_a_zero_close(self, pipeline: FeaturePipeline) -> None:
        bars = [
            candle(0, open_=0, high=0, low=0, close=0),
            candle(1, open_=1, high=1, low=1, close=1),
            candle(2, open_=2, high=2, low=2, close=2),
        ]
        run = pipeline.run("realized_volatility", bars, {"window": "2"})
        values = columns_of(run.output)["realized_volatility_2"]
        assert values[2] is None  # the zero-close return is undefined, so its window can't be


class TestRealizedVolatilityNoLookAhead:
    """VERIFY-VOLATILITY-FEATURE, Steps 1-2: the same adversarial no-look-ahead
    proof `TestNoLookAhead` (`tests/features/test_delta_market_data_features.py`)
    already requires of `funding_rate`/`open_interest` — a single, isolated
    "spike" candle whose effect on every other row's value is checked
    precisely, the same "poison the future, confirm the past is unaffected"
    shape, adapted for a rolling-window statistic instead of a step-function
    external value.

    A flat series (every close identical, so every log return is exactly
    0.0 and every trailing-window stdev is exactly 0.0) with one huge price
    jump at a single known row makes the feature's own window boundary
    directly observable: the jump can only ever change `pstdev(...)` away
    from 0.0 for the rows whose own trailing window actually contains it.
    """

    SPIKE_INDEX = 10
    WINDOW = 5

    def _bars(self, *, spike_close: float = 500.0, n: int = 20):  # noqa: ANN202 - test helper
        bars = [candle(i, open_=100, high=100, low=100, close=100) for i in range(n)]
        bars[self.SPIKE_INDEX] = candle(
            self.SPIKE_INDEX,
            open_=spike_close,
            high=spike_close,
            low=spike_close,
            close=spike_close,
        )
        return bars

    def test_worked_example_the_exact_window_boundary(self, pipeline: FeaturePipeline) -> None:
        """Step 1: the precise computation window, shown with real numbers,
        not described. `log_returns[j] = log(close[j] / close[j-1])` — the
        return *realized during* candle `j`, fully known once candle `j`
        has closed. Row `index`'s own value is `pstdev(log_returns[index -
        window + 1 : index + 1])` — inclusive of `log_returns[index]`
        itself (candle `index`'s own just-closed return) and nothing with
        a higher index. For `SPIKE_INDEX=10`, `WINDOW=5`: the spike return
        `log_returns[10] = log(500/100)` first enters row 10's own trailing
        window (`log_returns[6:11]`) and last appears in row 14's
        (`log_returns[10:15]`); row 9's own window is `log_returns[5:10]`
        — the slice upper bound `10` is *exclusive*, so index 9 (and
        therefore the spike return at index 10) is never included."""
        import math

        bars = self._bars()
        run = pipeline.run("realized_volatility", bars, {"window": str(self.WINDOW)})
        values = columns_of(run.output)[f"realized_volatility_{self.WINDOW}"]

        spike_return = math.log(500.0 / 100.0)
        assert spike_return == pytest.approx(1.6094, abs=1e-3)
        # Row 9's own window is log_returns[5:10] — strictly before the spike.
        assert values[9] == pytest.approx(0.0)
        # Row 10's own window is log_returns[6:11] — includes the spike (index 10).
        assert values[10] > 0.5

    def test_a_future_spike_never_changes_a_past_rows_value(
        self, pipeline: FeaturePipeline
    ) -> None:
        """The direct 'poison the future' proof: every row strictly before
        the spike is byte-identical whether or not the spike ever happens —
        computed from a completely disjoint, non-poisoned candle series
        truncated right before it, not merely asserted to be zero."""
        poisoned = self._bars()
        clean = poisoned[: self.SPIKE_INDEX]  # candles 0..9 only — the spike never happens

        poisoned_run = pipeline.run("realized_volatility", poisoned, {"window": str(self.WINDOW)})
        clean_run = pipeline.run("realized_volatility", clean, {"window": str(self.WINDOW)})

        poisoned_values = columns_of(poisoned_run.output)[f"realized_volatility_{self.WINDOW}"]
        clean_values = columns_of(clean_run.output)[f"realized_volatility_{self.WINDOW}"]

        # Every row that exists in both series (0..9) must match exactly —
        # the spike at index 10 must not reach backward into any of them.
        assert poisoned_values[: self.SPIKE_INDEX] == clean_values

    def test_the_window_has_a_hard_trailing_edge_the_spike_eventually_rolls_out_of(
        self, pipeline: FeaturePipeline
    ) -> None:
        """The window is *rolling*, not cumulative: once enough real hours
        have passed that neither anomalous return is among the trailing
        `WINDOW` returns, the feature must read exactly 0.0 again — proving
        the window is bounded on both sides, not merely non-negative on the
        left (Step 1's own boundary claim, from the other direction). A
        single spiked *candle* produces two anomalous *returns* — the jump
        in (`log_returns[10]`) and the jump back out
        (`log_returns[11]`) — so the affected rows are 10 through 15
        (whichever row's own trailing window contains either one), not
        just 10 through 14."""
        bars = self._bars(n=self.SPIKE_INDEX + self.WINDOW + 6)
        run = pipeline.run("realized_volatility", bars, {"window": str(self.WINDOW)})
        values = columns_of(run.output)[f"realized_volatility_{self.WINDOW}"]

        last_affected_row = (
            self.SPIKE_INDEX + self.WINDOW
        )  # 15: window [11, 15] still has return[11]
        for index in range(self.SPIKE_INDEX, last_affected_row + 1):
            assert values[index] > 0.5, f"row {index} should still see one of the two spikes"
        for index in range(last_affected_row + 1, len(bars)):
            assert values[index] == pytest.approx(0.0), f"row {index} should have rolled past it"


class TestIndicatorBackedFeatures:
    """SMA/EMA/WMA delegate to the indicator engine rather than reimplementing it."""

    def test_all_three_moving_averages_are_registered(self, pipeline: FeaturePipeline) -> None:
        for name in INDICATOR_BACKED_FEATURES:
            assert pipeline.registry.has(name)

    def test_sma_matches_the_indicator_engines_own_result(self, pipeline: FeaturePipeline) -> None:
        # The point of the adapter: one definition of SMA(3), so a dataset
        # column and a chart overlay can never disagree.
        bars = [candle(i, open_=10 + i, high=12 + i, low=9 + i, close=10 + i) for i in range(5)]
        load_builtin_indicators()
        engine = IndicatorEngine(default_indicator_registry)
        expected = engine.run("sma", bars, {"period": 3}).output.series[0].values

        run = pipeline.run("sma", bars, {"period": "3"})
        assert columns_of(run.output)["sma_3"] == expected

    def test_column_name_encodes_the_period(self, pipeline: FeaturePipeline) -> None:
        bars = [candle(i, open_=10, high=12, low=9, close=10 + i) for i in range(5)]
        run = pipeline.run("sma", bars, {"period": "3"})
        assert list(columns_of(run.output)) == ["sma_3"]

    def test_same_feature_at_two_periods_yields_distinct_columns(
        self, pipeline: FeaturePipeline
    ) -> None:
        # Without this, requesting SMA(20) and SMA(50) together would
        # collide into one column.
        bars = [candle(i, open_=10, high=12, low=9, close=10 + i) for i in range(6)]
        short = pipeline.run("sma", bars, {"period": "2"})
        long = pipeline.run("sma", bars, {"period": "4"})
        assert list(columns_of(short.output)) == ["sma_2"]
        assert list(columns_of(long.output)) == ["sma_4"]

    def test_a_non_default_source_is_visible_in_the_column_name(
        self, pipeline: FeaturePipeline
    ) -> None:
        # A column must never hide a parameter that changes its values.
        bars = [candle(i, open_=10, high=20 + i, low=9, close=10) for i in range(4)]
        run = pipeline.run("sma", bars, {"period": "2", "source": "high"})
        assert list(columns_of(run.output)) == ["sma_2_high"]

    def test_the_conventional_default_source_is_omitted_for_readability(self) -> None:
        assert _column_suffix({"period": 20, "source": "close"}) == "20"
        assert _column_suffix({"period": 20, "source": "high"}) == "20_high"
        assert _column_suffix({}) == ""

    def test_warmup_is_inherited_from_the_wrapped_indicator(
        self, pipeline: FeaturePipeline
    ) -> None:
        assert pipeline.warmup_for("sma", {"period": "20"}) == 20
        assert pipeline.warmup_for("ema", {"period": "12"}) == 12

    def test_metadata_is_derived_from_the_indicator_not_restated(
        self, pipeline: FeaturePipeline
    ) -> None:
        # Derived metadata cannot drift out of sync with the indicator.
        load_builtin_indicators()
        engine = IndicatorEngine(default_indicator_registry)
        indicator = engine.describe("wma")
        feature = pipeline.describe("wma")
        assert feature.label == indicator.label
        assert feature.description == indicator.description
        assert feature.category == indicator.category
        assert feature.complexity == indicator.complexity
        assert feature.aliases == indicator.aliases

    def test_parameter_validation_is_inherited_from_the_indicator(
        self, pipeline: FeaturePipeline
    ) -> None:
        bars = [candle(i, open_=10, high=12, low=9, close=10) for i in range(3)]
        with pytest.raises(InvalidFeatureParameterError, match="period"):
            pipeline.run("sma", bars, {"period": "0"})

    def test_exposes_the_indicator_it_delegates_to(self) -> None:
        load_builtin_indicators()
        engine = IndicatorEngine(default_indicator_registry)
        feature = IndicatorFeature("ema", engine)
        assert feature.indicator_name == "ema"
