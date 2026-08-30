"""Feature pipeline tests — validation, warmup, alignment, and error wrapping.

The pipeline's whole value is that every generator gets the same guarantees
without implementing them, so these tests exercise those guarantees against
deliberately-misbehaving generators rather than against the builtins.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
    OHLCVPoint,
    ParameterSpec,
)
from app.features.cache import FeatureCache
from app.features.errors import (
    FeatureExecutionError,
    FeatureNotFoundError,
    InsufficientFeatureDataError,
    InvalidFeatureParameterError,
)
from app.features.pipeline import PIPELINE_VERSION, FeaturePipeline
from app.features.registry import FeatureRegistry


def candles(count: int) -> list[OHLCVPoint]:
    """A simple ascending candle series."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVPoint(
            open_time=base + timedelta(hours=i),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=10.0 + i,
        )
        for i in range(count)
    ]


def one_column(name: str, values: list[Any]) -> FeatureOutput:
    return FeatureOutput(
        series=[FeatureSeries(column=FeatureColumn(name=name, label=name), values=values)]
    )


class Doubler(FeatureGenerator):
    """A well-behaved generator with one int parameter."""

    metadata = FeatureMetadata(
        name="doubler",
        label="Doubler",
        description="Close times a factor.",
        category="test",
        parameters=(
            ParameterSpec(
                name="factor",
                type="int",
                label="Factor",
                description="Multiplier.",
                default=2,
                minimum=1,
                maximum=10,
            ),
        ),
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        factor = ctx.int_param("factor")
        return one_column("doubled", [c.close * factor for c in ctx.candles])


class WarmingUp(FeatureGenerator):
    """Warmup equals its period parameter."""

    metadata = FeatureMetadata(
        name="warming_up",
        label="Warming Up",
        description="Null until the period is reached.",
        category="test",
        parameters=(
            ParameterSpec(
                name="period",
                type="int",
                label="Period",
                description="Warmup length.",
                default=3,
                minimum=1,
            ),
        ),
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        return int(params["period"])

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        period = ctx.int_param("period")
        values = [None if i < period - 1 else float(i) for i in range(len(ctx.candles))]
        return one_column("warm", values)


class Misaligned(FeatureGenerator):
    """Returns fewer values than there are candles — the silent-corruption case."""

    metadata = FeatureMetadata(
        name="misaligned", label="Misaligned", description="Broken.", category="test"
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        return one_column("broken", [1.0] * (len(ctx.candles) - 1))


class Exploding(FeatureGenerator):
    """Raises during generation."""

    metadata = FeatureMetadata(
        name="exploding", label="Exploding", description="Broken.", category="test"
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        raise ValueError("boom")


class ExplodingWarmup(FeatureGenerator):
    """Raises from warmup() rather than generate()."""

    metadata = FeatureMetadata(
        name="exploding_warmup", label="Exploding Warmup", description="Broken.", category="test"
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        raise ValueError("bad warmup")

    def generate(self, ctx: FeatureContext) -> FeatureOutput:  # pragma: no cover
        raise AssertionError("never reached")


class NoColumns(FeatureGenerator):
    """Returns an empty output."""

    metadata = FeatureMetadata(
        name="no_columns", label="No Columns", description="Broken.", category="test"
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        return FeatureOutput(series=[])


class RepeatedColumn(FeatureGenerator):
    """Returns the same column name twice."""

    metadata = FeatureMetadata(
        name="repeated", label="Repeated", description="Broken.", category="test"
    )

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        values = [1.0] * len(ctx.candles)
        column = FeatureColumn(name="same", label="Same")
        return FeatureOutput(
            series=[
                FeatureSeries(column=column, values=values),
                FeatureSeries(column=column, values=values),
            ]
        )


class NegativeWarmup(FeatureGenerator):
    """Reports a negative warmup, which must be clamped rather than trusted."""

    metadata = FeatureMetadata(
        name="negative", label="Negative", description="Odd.", category="test"
    )

    def warmup(self, params: Mapping[str, Any]) -> int:
        return -5

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        return one_column("value", [1.0] * len(ctx.candles))


class Counting(FeatureGenerator):
    """Counts how many times `generate()` actually ran — the cache probe.

    A cache hit must skip `generate()` entirely, not merely return an
    equal-looking value; this is what lets a test tell "recomputed and
    happened to match" from "never recomputed at all".
    """

    metadata = FeatureMetadata(
        name="counting", label="Counting", description="Counts its own calls.", category="test"
    )
    calls: int = 0

    def generate(self, ctx: FeatureContext) -> FeatureOutput:
        Counting.calls += 1
        return one_column("count", [float(Counting.calls)] * len(ctx.candles))


@pytest.fixture
def pipeline() -> FeaturePipeline:
    """An isolated pipeline holding only this module's test generators."""
    registry = FeatureRegistry()
    for cls in (
        Doubler,
        WarmingUp,
        Misaligned,
        Exploding,
        ExplodingWarmup,
        NoColumns,
        RepeatedColumn,
        NegativeWarmup,
        Counting,
    ):
        registry.register(cls)
    return FeaturePipeline(registry)


@pytest.fixture
def cached_pipeline() -> FeaturePipeline:
    """The same test registry, wired to a real `FeatureCache`."""
    Counting.calls = 0
    registry = FeatureRegistry()
    for cls in (Doubler, Counting):
        registry.register(cls)
    return FeaturePipeline(registry, FeatureCache())


class TestExecution:
    def test_runs_a_generator_and_returns_its_columns(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("doubler", candles(3), {"factor": "2"})
        assert run.output.series[0].column.name == "doubled"
        assert run.output.series[0].values == [204.0, 206.0, 208.0]

    def test_reports_the_resolved_parameters_including_defaults(
        self, pipeline: FeaturePipeline
    ) -> None:
        run = pipeline.run("doubler", candles(2))
        assert run.params == {"factor": 2}

    def test_coerces_string_parameters_from_a_json_or_query_layer(
        self, pipeline: FeaturePipeline
    ) -> None:
        run = pipeline.run("doubler", candles(1), {"factor": "3"})
        assert run.params == {"factor": 3}
        assert run.output.series[0].values == [306.0]

    def test_reports_execution_timing(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("doubler", candles(2))
        assert run.execution_time_ms >= 0.0

    def test_exposes_the_generators_metadata_on_the_run(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("doubler", candles(2))
        assert run.metadata.name == "doubler"
        assert run.metadata.version == "1.0.0"

    def test_pipeline_version_is_reported_for_reproducibility(self) -> None:
        assert PIPELINE_VERSION

    def test_reports_cache_disabled_when_no_cache_is_wired(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.run("doubler", candles(2)).cache_status == "disabled"


class TestCatalogue:
    def test_describes_every_registered_generator(self, pipeline: FeaturePipeline) -> None:
        names = {entry.name for entry in pipeline.describe_all()}
        assert {"doubler", "warming_up"} <= names

    def test_describes_one_generator(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.describe("doubler").label == "Doubler"

    def test_raises_for_an_unknown_generator(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(FeatureNotFoundError):
            pipeline.describe("nope")

    def test_exposes_its_registry(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.registry.has("doubler")


class TestWarmup:
    def test_reports_a_generators_warmup_without_running_it(
        self, pipeline: FeaturePipeline
    ) -> None:
        # The dataset builder needs this before loading candles, to widen
        # the window so trimming doesn't shrink the requested row count.
        assert pipeline.warmup_for("warming_up", {"period": "5"}) == 5

    def test_warmup_uses_defaults_when_no_parameters_are_supplied(
        self, pipeline: FeaturePipeline
    ) -> None:
        assert pipeline.warmup_for("warming_up") == 3

    def test_defaults_to_zero_warmup(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.warmup_for("doubler") == 0

    def test_clamps_a_negative_warmup_to_zero(self, pipeline: FeaturePipeline) -> None:
        assert pipeline.warmup_for("negative") == 0

    def test_wraps_a_failure_inside_warmup_as_a_named_error(
        self, pipeline: FeaturePipeline
    ) -> None:
        with pytest.raises(FeatureExecutionError, match="exploding_warmup"):
            pipeline.warmup_for("exploding_warmup")

    def test_reports_warmup_on_the_run(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("warming_up", candles(6), {"period": "4"})
        assert run.warmup == 4


class TestValidation:
    def test_rejects_an_out_of_range_parameter(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(InvalidFeatureParameterError) as exc_info:
            pipeline.run("doubler", candles(2), {"factor": "0"})
        assert exc_info.value.code == "invalid_feature_parameter"
        assert "factor" in exc_info.value.message

    def test_error_names_the_feature_not_an_indicator_the_caller_never_asked_for(
        self, pipeline: FeaturePipeline
    ) -> None:
        # validate_parameters is reused from the indicator engine, so the
        # raised error type must be translated for this context.
        with pytest.raises(InvalidFeatureParameterError) as exc_info:
            pipeline.run("doubler", candles(2), {"factor": "99"})
        assert "doubler" in exc_info.value.message

    def test_recommends_the_declared_default_on_a_bound_violation(
        self, pipeline: FeaturePipeline
    ) -> None:
        with pytest.raises(InvalidFeatureParameterError) as exc_info:
            pipeline.run("doubler", candles(2), {"factor": "0"})
        assert "(recommended: 2)" in exc_info.value.message

    def test_rejects_an_unknown_parameter_rather_than_ignoring_it(
        self, pipeline: FeaturePipeline
    ) -> None:
        # A typo that silently fell back to a default would produce a
        # plausible-looking but wrong dataset.
        with pytest.raises(InvalidFeatureParameterError, match="not accepted"):
            pipeline.run("doubler", candles(2), {"factr": "2"})

    def test_rejects_a_non_numeric_parameter(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(InvalidFeatureParameterError):
            pipeline.run("doubler", candles(2), {"factor": "two"})

    def test_raises_for_an_unknown_generator(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(FeatureNotFoundError):
            pipeline.run("nope", candles(2))


class TestGuarantees:
    def test_rejects_a_misaligned_column(self, pipeline: FeaturePipeline) -> None:
        # The one contract a generator can break silently: a misaligned
        # column still serializes, still exports, and still trains a model
        # — against the wrong timestamps.
        with pytest.raises(FeatureExecutionError, match="must align"):
            pipeline.run("misaligned", candles(4))

    def test_rejects_an_empty_output(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(FeatureExecutionError, match="no output columns"):
            pipeline.run("no_columns", candles(2))

    def test_rejects_a_repeated_column_within_one_generator(
        self, pipeline: FeaturePipeline
    ) -> None:
        with pytest.raises(FeatureExecutionError, match="more than once"):
            pipeline.run("repeated", candles(2))

    def test_rejects_a_range_shorter_than_the_warmup_as_a_400(
        self, pipeline: FeaturePipeline
    ) -> None:
        # Must be a client error naming the shortfall, never a 500: it is
        # the request that is wrong, not the generator.
        with pytest.raises(InsufficientFeatureDataError) as exc_info:
            pipeline.run("warming_up", candles(2), {"period": "5"})
        assert exc_info.value.status_code == 400
        assert exc_info.value.required == 5
        assert exc_info.value.available == 2
        assert "warming_up" in exc_info.value.message

    def test_accepts_a_range_exactly_equal_to_the_warmup(self, pipeline: FeaturePipeline) -> None:
        run = pipeline.run("warming_up", candles(3), {"period": "3"})
        assert run.output.series[0].values[-1] is not None

    def test_wraps_a_generator_bug_as_a_named_500(self, pipeline: FeaturePipeline) -> None:
        with pytest.raises(FeatureExecutionError) as exc_info:
            pipeline.run("exploding", candles(2))
        assert exc_info.value.status_code == 500
        assert "exploding" in exc_info.value.message
        assert "ValueError" in exc_info.value.message


class TestCache:
    def test_first_run_is_a_miss_and_actually_computes(
        self, cached_pipeline: FeaturePipeline
    ) -> None:
        run = cached_pipeline.run("counting", candles(3))
        assert run.cache_status == "miss"
        assert Counting.calls == 1

    def test_identical_second_call_is_a_hit_and_skips_recomputation(
        self, cached_pipeline: FeaturePipeline
    ) -> None:
        first = cached_pipeline.run("counting", candles(3))
        second = cached_pipeline.run("counting", candles(3))
        assert second.cache_status == "hit"
        assert Counting.calls == 1  # generate() ran exactly once, not twice
        assert second.output.series[0].values == first.output.series[0].values

    def test_different_params_do_not_collide(self, cached_pipeline: FeaturePipeline) -> None:
        cached_pipeline.run("doubler", candles(3), {"factor": "2"})
        run = cached_pipeline.run("doubler", candles(3), {"factor": "3"})
        assert run.cache_status == "miss"

    def test_different_candle_ranges_do_not_collide(
        self, cached_pipeline: FeaturePipeline
    ) -> None:
        cached_pipeline.run("counting", candles(3))
        run = cached_pipeline.run("counting", candles(4))
        assert run.cache_status == "miss"
        assert Counting.calls == 2

    def test_a_cache_hit_still_reports_the_generators_metadata(
        self, cached_pipeline: FeaturePipeline
    ) -> None:
        cached_pipeline.run("counting", candles(2))
        run = cached_pipeline.run("counting", candles(2))
        assert run.metadata.name == "counting"
        assert run.warmup == 0
