"""Execution pipeline tests.

Covers the stages the engine applies to *every* indicator: parameter
validation, the warmup guard, caching, error containment, and the
output-alignment contract. Deliberately uses purpose-built stub indicators
rather than the real SMA/EMA/RSI, so a change to a builtin's maths can
never make a pipeline test pass or fail for the wrong reason.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.indicators.base import (
    Indicator,
    IndicatorContext,
    IndicatorMetadata,
    IndicatorOutput,
    IndicatorSeries,
    OHLCVPoint,
    SeriesSpec,
)
from app.indicators.cache import IndicatorCache
from app.indicators.engine import IndicatorEngine
from app.indicators.errors import (
    IndicatorExecutionError,
    IndicatorNotFoundError,
    InsufficientDataError,
    InvalidIndicatorParameterError,
)
from app.indicators.params import ParameterSpec
from app.indicators.registry import IndicatorRegistry

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def candles(count: int, *, close: float = 100.0) -> list[OHLCVPoint]:
    """``count`` hourly candles with a predictable rising close."""
    return [
        OHLCVPoint(
            open_time=BASE + timedelta(hours=index),
            open=close + index,
            high=close + index + 1,
            low=close + index - 1,
            close=close + index,
            volume=10.0,
        )
        for index in range(count)
    ]


class Doubler(Indicator):
    """Doubles the close; one optional ``period`` driving a fixed warmup."""

    metadata = IndicatorMetadata(
        name="doubler",
        label="Doubler",
        description="Stub indicator.",
        category="test",
        parameters=(
            ParameterSpec(
                name="period",
                type="int",
                label="Period",
                description="Warmup length.",
                default=3,
                minimum=1,
                maximum=50,
            ),
        ),
        outputs=(SeriesSpec(name="doubled", label="Doubled"),),
    )

    def warmup(self, params):  # type: ignore[no-untyped-def]
        return int(params["period"])

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        period = ctx.int_param("period")
        values: list[float | None] = [
            None if index < period - 1 else candle.close * 2
            for index, candle in enumerate(ctx.candles)
        ]
        return IndicatorOutput(
            series=[IndicatorSeries(name="doubled", label="Doubled", values=values)]
        )


class Exploding(Indicator):
    """Always raises, to exercise the engine's error containment."""

    metadata = IndicatorMetadata(
        name="exploding",
        label="Exploding",
        description="Stub indicator that raises.",
        category="test",
    )

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        raise ZeroDivisionError("boom")


class Misaligned(Indicator):
    """Returns fewer values than candles, violating the alignment contract."""

    metadata = IndicatorMetadata(
        name="misaligned",
        label="Misaligned",
        description="Stub indicator with a short series.",
        category="test",
    )

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        return IndicatorOutput(series=[IndicatorSeries(name="short", label="Short", values=[1.0])])


class Empty(Indicator):
    """Returns no series at all."""

    metadata = IndicatorMetadata(
        name="empty",
        label="Empty",
        description="Stub indicator with no output.",
        category="test",
    )

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        return IndicatorOutput(series=[])


class BadWarmup(Indicator):
    """Raises from ``warmup()`` rather than from ``calculate()``."""

    metadata = IndicatorMetadata(
        name="bad_warmup",
        label="Bad Warmup",
        description="Stub indicator with a broken warmup.",
        category="test",
    )

    def warmup(self, params):  # type: ignore[no-untyped-def]
        raise ValueError("cannot compute warmup")

    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        raise AssertionError("should never be reached")


@pytest.fixture
def registry() -> IndicatorRegistry:
    """An isolated registry holding only the stub indicators."""
    reg = IndicatorRegistry()
    for cls in (Doubler, Exploding, Misaligned, Empty, BadWarmup):
        reg.register(cls)
    return reg


@pytest.fixture
def engine(registry: IndicatorRegistry) -> IndicatorEngine:
    """An engine with caching disabled (the default for most assertions)."""
    return IndicatorEngine(registry)


class TestResolution:
    def test_runs_a_registered_indicator(self, engine: IndicatorEngine) -> None:
        run = engine.run("doubler", candles(5))
        assert run.output.series[0].values[-1] == pytest.approx(208.0)

    def test_raises_for_an_unregistered_indicator(self, engine: IndicatorEngine) -> None:
        with pytest.raises(IndicatorNotFoundError):
            engine.run("nope", candles(5))

    def test_describe_all_lists_every_registered_indicator(self, engine: IndicatorEngine) -> None:
        names = [entry.name for entry in engine.describe_all()]
        assert names == ["bad_warmup", "doubler", "empty", "exploding", "misaligned"]

    def test_describe_returns_one_indicator_metadata(self, engine: IndicatorEngine) -> None:
        assert engine.describe("doubler").label == "Doubler"

    def test_describe_raises_for_an_unknown_indicator(self, engine: IndicatorEngine) -> None:
        with pytest.raises(IndicatorNotFoundError):
            engine.describe("nope")


class TestParameterValidation:
    def test_applies_declared_defaults_when_omitted(self, engine: IndicatorEngine) -> None:
        run = engine.run("doubler", candles(5))
        assert run.params == {"period": 3}

    def test_coerces_string_parameters_from_the_query_layer(self, engine: IndicatorEngine) -> None:
        run = engine.run("doubler", candles(5), {"period": "2"})
        assert run.params == {"period": 2}

    def test_rejects_an_out_of_range_parameter_before_calculating(
        self, engine: IndicatorEngine
    ) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="must be >= 1"):
            engine.run("doubler", candles(5), {"period": "0"})

    def test_rejects_an_unknown_parameter(self, engine: IndicatorEngine) -> None:
        with pytest.raises(InvalidIndicatorParameterError, match="is not accepted"):
            engine.run("doubler", candles(5), {"windo": "3"})


class TestWarmupGuard:
    def test_rejects_a_range_shorter_than_the_warmup(self, engine: IndicatorEngine) -> None:
        with pytest.raises(InsufficientDataError) as exc_info:
            engine.run("doubler", candles(2), {"period": "5"})
        assert exc_info.value.required == 5
        assert exc_info.value.available == 2

    def test_accepts_a_range_exactly_equal_to_the_warmup(self, engine: IndicatorEngine) -> None:
        run = engine.run("doubler", candles(5), {"period": "5"})
        assert run.warmup == 5

    def test_reports_the_warmup_used(self, engine: IndicatorEngine) -> None:
        assert engine.run("doubler", candles(10), {"period": "4"}).warmup == 4

    def test_a_broken_warmup_surfaces_as_a_named_execution_error(
        self, engine: IndicatorEngine
    ) -> None:
        with pytest.raises(IndicatorExecutionError, match="warmup\\(\\) raised ValueError"):
            engine.run("bad_warmup", candles(5))


class TestErrorContainment:
    def test_wraps_an_indicator_exception_in_a_named_domain_error(
        self, engine: IndicatorEngine
    ) -> None:
        # A bug in one indicator must not surface as an anonymous 500.
        with pytest.raises(IndicatorExecutionError) as exc_info:
            engine.run("exploding", candles(5))
        assert exc_info.value.indicator == "exploding"
        assert "ZeroDivisionError" in exc_info.value.message
        assert exc_info.value.status_code == 500

    def test_preserves_the_original_exception_as_the_cause(self, engine: IndicatorEngine) -> None:
        with pytest.raises(IndicatorExecutionError) as exc_info:
            engine.run("exploding", candles(5))
        assert isinstance(exc_info.value.__cause__, ZeroDivisionError)


class TestAlignmentContract:
    def test_rejects_a_series_shorter_than_the_input(self, engine: IndicatorEngine) -> None:
        # A misaligned series would still plot — against the wrong
        # timestamps, which is the worst kind of wrong.
        with pytest.raises(IndicatorExecutionError, match="must align with the input"):
            engine.run("misaligned", candles(5))

    def test_rejects_an_indicator_that_returns_no_series(self, engine: IndicatorEngine) -> None:
        with pytest.raises(IndicatorExecutionError, match="returned no output series"):
            engine.run("empty", candles(5))

    def test_a_valid_series_matches_the_candle_count(self, engine: IndicatorEngine) -> None:
        run = engine.run("doubler", candles(7))
        assert len(run.output.series[0].values) == 7


class TestCaching:
    def test_reports_disabled_when_no_cache_is_configured(self, engine: IndicatorEngine) -> None:
        assert engine.run("doubler", candles(5)).cache_status == "disabled"

    def test_first_run_misses_and_second_run_hits(self, registry: IndicatorRegistry) -> None:
        cached = IndicatorEngine(registry, IndicatorCache())
        data = candles(5)
        assert cached.run("doubler", data, {"period": "3"}).cache_status == "miss"
        assert cached.run("doubler", data, {"period": "3"}).cache_status == "hit"

    def test_a_cache_hit_returns_the_same_values(self, registry: IndicatorRegistry) -> None:
        cached = IndicatorEngine(registry, IndicatorCache())
        data = candles(5)
        first = cached.run("doubler", data, {"period": "3"})
        second = cached.run("doubler", data, {"period": "3"})
        assert second.output.series[0].values == first.output.series[0].values

    def test_different_parameters_do_not_share_a_cache_entry(
        self, registry: IndicatorRegistry
    ) -> None:
        cached = IndicatorEngine(registry, IndicatorCache())
        data = candles(6)
        cached.run("doubler", data, {"period": "2"})
        assert cached.run("doubler", data, {"period": "3"}).cache_status == "miss"

    def test_different_candles_do_not_share_a_cache_entry(
        self, registry: IndicatorRegistry
    ) -> None:
        cached = IndicatorEngine(registry, IndicatorCache())
        cached.run("doubler", candles(5))
        assert cached.run("doubler", candles(6)).cache_status == "miss"

    def test_a_changed_final_close_invalidates_the_entry(self, registry: IndicatorRegistry) -> None:
        # The forming-candle case: same count, same open times, new close.
        cached = IndicatorEngine(registry, IndicatorCache())
        original = candles(5)
        cached.run("doubler", original)
        mutated = [
            *original[:-1],
            OHLCVPoint(
                open_time=original[-1].open_time,
                open=original[-1].open,
                high=original[-1].high,
                low=original[-1].low,
                close=original[-1].close + 1,
                volume=original[-1].volume,
            ),
        ]
        assert cached.run("doubler", mutated).cache_status == "miss"


class TestRunMetadata:
    def test_returns_the_indicator_metadata_it_ran(self, engine: IndicatorEngine) -> None:
        assert engine.run("doubler", candles(5)).metadata.name == "doubler"

    def test_reports_a_non_negative_execution_time(self, engine: IndicatorEngine) -> None:
        assert engine.run("doubler", candles(5)).execution_time_ms >= 0.0

    def test_exposes_its_registry(self, registry: IndicatorRegistry) -> None:
        assert IndicatorEngine(registry).registry is registry
