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
