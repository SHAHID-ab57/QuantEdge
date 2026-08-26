"""Target pipeline tests — parameter validation, horizon, alignment, uniqueness.

Mirrors `tests/features/test_pipeline.py`'s convention: tested against
isolated, throwaway generators (never the real builtins), so a pipeline
test failure always means the *pipeline* is broken, never a coincidence of
one generator's own maths.
"""

import pytest

from app.ml_datasets.base import (
    TargetColumn,
    TargetContext,
    TargetGenerator,
    TargetMetadata,
    TargetOutput,
    TargetSeries,
)
from app.ml_datasets.errors import (
    InsufficientTargetDataError,
    InvalidTargetParameterError,
    TargetExecutionError,
)
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import TargetRegistry
from app.ml_datasets.targets.common import HORIZON_PARAMETER
from tests.ml_datasets.conftest import candles


def _column(name: str = "value") -> TargetColumn:
    return TargetColumn(name=name, label=name, dtype="float")


class Doubler(TargetGenerator):
    """A well-behaved target: doubles the close, `horizon` candles ahead."""

    metadata = TargetMetadata(
        name="doubler",
        label="Doubler",
        description="",
        category="test",
        parameters=(HORIZON_PARAMETER,),
        default_horizon=1,
    )

    def generate(self, ctx: TargetContext) -> TargetOutput:
        horizon = ctx.int_param("horizon")
        count = len(ctx.candles)
        values = []
        for index in range(count):
            if index < count - horizon:
                values.append(float(ctx.candles[index + horizon].close) * 2)
            else:
                values.append(None)
        return TargetOutput(series=[TargetSeries(column=_column(), values=values)])


class Misaligned(TargetGenerator):
    metadata = TargetMetadata(
        name="misaligned", label="Misaligned", description="", category="test"
    )

    def generate(self, ctx: TargetContext) -> TargetOutput:
        return TargetOutput(series=[TargetSeries(column=_column(), values=[1.0, 2.0])])


class Empty(TargetGenerator):
    metadata = TargetMetadata(name="empty", label="Empty", description="", category="test")

    def generate(self, ctx: TargetContext) -> TargetOutput:
        return TargetOutput(series=[])


class Exploding(TargetGenerator):
    metadata = TargetMetadata(name="exploding", label="Exploding", description="", category="test")

    def generate(self, ctx: TargetContext) -> TargetOutput:
        raise RuntimeError("boom")


class DuplicateColumns(TargetGenerator):
    metadata = TargetMetadata(name="dupes", label="Dupes", description="", category="test")

    def generate(self, ctx: TargetContext) -> TargetOutput:
        values = [None] * len(ctx.candles)
        return TargetOutput(
            series=[
                TargetSeries(column=_column("same"), values=values),
                TargetSeries(column=_column("same"), values=values),
            ]
        )


class BadHorizon(TargetGenerator):
    metadata = TargetMetadata(
        name="bad_horizon", label="Bad Horizon", description="", category="test"
    )

    def horizon(self, params):
        raise ValueError("no horizon for you")

    def generate(self, ctx: TargetContext) -> TargetOutput:
        return TargetOutput(series=[TargetSeries(column=_column(), values=[])])


@pytest.fixture
def registry() -> TargetRegistry:
    registry = TargetRegistry()
    for generator_cls in (Doubler, Misaligned, Empty, Exploding, DuplicateColumns, BadHorizon):
        registry.register(generator_cls)
    return registry


@pytest.fixture
def pipeline(registry: TargetRegistry) -> TargetPipeline:
    return TargetPipeline(registry)


class TestRun:
    def test_generates_a_well_behaved_target(self, pipeline: TargetPipeline) -> None:
        run = pipeline.run("doubler", candles(5), {"horizon": 1})
        assert run.output.series[0].values == [202.0, 204.0, 206.0, 208.0, None]
        assert run.horizon == 1

    def test_default_horizon_applies_when_unspecified(self, pipeline: TargetPipeline) -> None:
        run = pipeline.run("doubler", candles(5))
        assert run.horizon == 1

    def test_rejects_an_unknown_parameter(self, pipeline: TargetPipeline) -> None:
        with pytest.raises(InvalidTargetParameterError):
            pipeline.run("doubler", candles(5), {"nonsense": 1})

    def test_rejects_an_under_sized_range_for_the_horizon(self, pipeline: TargetPipeline) -> None:
        with pytest.raises(InsufficientTargetDataError) as exc_info:
            pipeline.run("doubler", candles(2), {"horizon": 5})
        assert exc_info.value.horizon == 5
        assert exc_info.value.available == 2

    def test_rejects_misaligned_output(self, pipeline: TargetPipeline) -> None:
        with pytest.raises(TargetExecutionError, match="must align"):
            pipeline.run("misaligned", candles(5))

    def test_rejects_a_generator_with_no_output_columns(self, pipeline: TargetPipeline) -> None:
        with pytest.raises(TargetExecutionError, match="no output columns"):
            pipeline.run("empty", candles(5))

    def test_wraps_an_unexpected_exception(self, pipeline: TargetPipeline) -> None:
        with pytest.raises(TargetExecutionError, match="RuntimeError"):
            pipeline.run("exploding", candles(5))

    def test_rejects_duplicate_column_names_from_one_generator(
        self, pipeline: TargetPipeline
    ) -> None:
        with pytest.raises(TargetExecutionError, match="more than once"):
            pipeline.run("dupes", candles(5))

    def test_a_horizon_method_that_raises_is_a_named_error(self, pipeline: TargetPipeline) -> None:
        with pytest.raises(TargetExecutionError, match="horizon\\(\\) raised"):
            pipeline.run("bad_horizon", candles(5))


class TestHorizonFor:
    def test_reports_the_horizon_without_running_the_generator(
        self, pipeline: TargetPipeline
    ) -> None:
        assert pipeline.horizon_for("doubler", {"horizon": 3}) == 3

    def test_defaults_when_unspecified(self, pipeline: TargetPipeline) -> None:
        assert pipeline.horizon_for("doubler") == 1


class ZeroHorizon(TargetGenerator):
    """A target with no horizon at all — every row is immediately defined."""

    metadata = TargetMetadata(
        name="zero_horizon", label="Zero Horizon", description="", category="test"
    )

    def horizon(self, params) -> int:
        return 0

    def generate(self, ctx: TargetContext) -> TargetOutput:
        return TargetOutput(
            series=[TargetSeries(column=_column(), values=[1.0] * len(ctx.candles))]
        )


class TestZeroHorizon:
    def test_a_zero_horizon_target_never_trims_anything(self) -> None:
        registry = TargetRegistry()
        registry.register(ZeroHorizon)
        run = TargetPipeline(registry).run("zero_horizon", candles(5))
        assert run.horizon == 0
        assert run.output.series[0].values == [1.0, 1.0, 1.0, 1.0, 1.0]


class TestContextParamHelpers:
    def test_float_and_str_param_read_validated_values(self) -> None:
        ctx = TargetContext(candles=candles(3), params={"threshold": 0.5, "label": "up"})
        assert ctx.float_param("threshold") == 0.5
        assert ctx.str_param("label") == "up"


class TestRegistryProperty:
    def test_exposes_the_registry_it_resolves_from(
        self, pipeline: TargetPipeline, registry: TargetRegistry
    ) -> None:
        assert pipeline.registry is registry


class TestDescribe:
    def test_describe_all_lists_every_registered_generator(self, pipeline: TargetPipeline) -> None:
        names = {metadata.name for metadata in pipeline.describe_all()}
        assert "doubler" in names

    def test_describe_returns_one_generators_metadata(self, pipeline: TargetPipeline) -> None:
        assert pipeline.describe("doubler").category == "test"
