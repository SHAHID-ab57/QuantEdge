"""Builtin target generator tests — correctness and the forward-looking contract."""

import pytest

from app.ml_datasets.errors import TargetAlignmentError
from app.ml_datasets.registry import TargetRegistry
from app.ml_datasets.targets.next_close import NextClosePrice
from app.ml_datasets.targets.next_direction import NextDirection
from app.ml_datasets.targets.next_return import NextReturn
from tests.ml_datasets.conftest import candles


def series_for(generator_cls, params: dict | None = None, count: int = 5):
    """Run one generator directly (no pipeline) and return its single output series."""
    from app.ml_datasets.base import TargetContext

    generator = generator_cls()
    horizon = generator.horizon(params or {"horizon": 1})
    ctx = TargetContext(candles=candles(count), params={"horizon": horizon, **(params or {})})
    output = generator.generate(ctx)
    assert len(output.series) == 1
    return output.series[0]


class TestNextClosePrice:
    def test_each_row_equals_the_close_horizon_candles_ahead(self) -> None:
        series = series_for(NextClosePrice, {"horizon": 1}, count=5)
        # candles() closes are 100, 101, 102, 103, 104
        assert series.values == [101.0, 102.0, 103.0, 104.0, None]

    def test_a_larger_horizon_looks_further_ahead(self) -> None:
        series = series_for(NextClosePrice, {"horizon": 2}, count=5)
        # boundary = 5 - 2 = 3, so indices 0..2 are defined (candles[i+2]) and
        # the trailing two rows (3, 4) have no candle two ahead of them.
        assert series.values == [102.0, 103.0, 104.0, None, None]

    def test_column_name_encodes_the_horizon(self) -> None:
        series = series_for(NextClosePrice, {"horizon": 3}, count=6)
        assert series.column.name == "next_close_3"

    def test_column_is_declared_float(self) -> None:
        series = series_for(NextClosePrice, {"horizon": 1})
        assert series.column.dtype == "float"


class TestNextReturn:
    def test_return_is_the_fractional_change_to_the_future_close(self) -> None:
        series = series_for(NextReturn, {"horizon": 1}, count=3)
        # (101 - 100) / 100 = 0.01; (102 - 101) / 101 ≈ 0.0099...
        assert series.values[0] == pytest.approx(0.01)
        assert series.values[1] == pytest.approx((102.0 - 101.0) / 101.0)
        assert series.values[2] is None

    def test_never_divides_by_a_zero_current_close(self) -> None:
        from app.ml_datasets.base import TargetContext

        zeroed = candles(3)
        zeroed[0] = zeroed[0].__class__(
            open_time=zeroed[0].open_time,
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0.0,
        )
        generator = NextReturn()
        ctx = TargetContext(candles=zeroed, params={"horizon": 1})
        output = generator.generate(ctx)
        assert output.series[0].values[0] is None


class TestNextDirection:
    def test_classifies_up_down_and_flat(self) -> None:
        from app.ml_datasets.base import TargetContext

        flat_then_up_then_down = candles(4)
        # Force row 1's close to equal row 2's close for a "flat" case.
        c = list(flat_then_up_then_down)
        c[2] = c[2].__class__(
            open_time=c[2].open_time,
            open=c[1].close,
            high=c[1].close,
            low=c[1].close,
            close=c[1].close,
            volume=c[2].volume,
        )
        generator = NextDirection()
        output = generator.generate(TargetContext(candles=c, params={"horizon": 1}))
        values = output.series[0].values
        assert values[0] == "up"  # 100 -> 101
        assert values[1] == "flat"  # 101 -> 101 (forced)
        assert values[3] is None

    def test_classifies_down(self) -> None:
        from app.ml_datasets.base import TargetContext

        base = candles(3, start_price=100.0)
        descending = [
            base[0],
            base[0].__class__(
                open_time=base[1].open_time,
                open=90.0,
                high=95.0,
                low=85.0,
                close=90.0,
                volume=base[1].volume,
            ),
        ]
        generator = NextDirection()
        output = generator.generate(TargetContext(candles=descending, params={"horizon": 1}))
        assert output.series[0].values[0] == "down"

    def test_column_is_declared_categorical(self) -> None:
        series = series_for(NextDirection, {"horizon": 1})
        assert series.column.dtype == "categorical"


class TestForwardLookingContractIsEnforced:
    """A misbehaving generator is caught by the pipeline, not silently trusted."""

    def test_a_generator_that_fills_in_the_trailing_horizon_is_rejected(self) -> None:
        from app.ml_datasets.base import (
            TargetContext,
            TargetGenerator,
            TargetMetadata,
            TargetOutput,
            TargetSeries,
        )
        from app.ml_datasets.pipeline import TargetPipeline

        class _Cheater(TargetGenerator):
            metadata = TargetMetadata(
                name="cheater", label="Cheater", description="", category="test", default_horizon=1
            )

            def generate(self, ctx: TargetContext) -> TargetOutput:
                from app.ml_datasets.base import TargetColumn

                # Fabricates a value for the very last row, which has no
                # future candle — exactly the bug this contract exists to catch.
                values = [1.0] * len(ctx.candles)
                column = TargetColumn(name="cheat", label="Cheat", dtype="float")
                return TargetOutput(series=[TargetSeries(column=column, values=values)])

        registry = TargetRegistry()
        registry.register(_Cheater)
        pipeline = TargetPipeline(registry)
        with pytest.raises(TargetAlignmentError):
            pipeline.run("cheater", candles(5))
