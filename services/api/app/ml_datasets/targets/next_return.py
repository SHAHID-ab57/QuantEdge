"""Next candle return — percentage price change, `horizon` candles ahead."""

from app.ml_datasets.base import (
    TargetColumn,
    TargetContext,
    TargetGenerator,
    TargetMetadata,
    TargetOutput,
    TargetSeries,
)
from app.ml_datasets.registry import register
from app.ml_datasets.targets.common import HORIZON_PARAMETER


@register
class NextReturn(TargetGenerator):
    """The fractional price change from each row's `close` to `horizon` candles ahead.

    ``(future_close - current_close) / current_close`` — a unitless ratio,
    comparable across markets and price levels the way a raw price
    difference is not, which is the usual reason a return target is
    preferred over a raw future price for training a model across more
    than one instrument.
    """

    metadata = TargetMetadata(
        name="next_return",
        label="Next Candle Return",
        description=(
            "Fractional price change from this row's close to the close `horizon` "
            "candles ahead: (future - current) / current."
        ),
        category="return",
        parameters=(HORIZON_PARAMETER,),
        outputs=("next_return_{horizon}",),
        value_type="float",
        is_deterministic=True,
        # A row whose *current* close is exactly zero has an undefined
        # percentage return — reported as a null rather than raising or
        # dividing by zero, the same "null marks undefined, never
        # fabricated" contract every generator in this platform follows.
        # Real market data never has a zero close, but the generator must
        # not crash if it somehow did.
    )

    def generate(self, ctx: TargetContext) -> TargetOutput:
        horizon = ctx.int_param("horizon")
        candles = ctx.candles
        name = f"next_return_{horizon}"

        values = []
        boundary = len(candles) - horizon
        for index, candle in enumerate(candles):
            if index >= boundary or float(candle.close) == 0.0:
                values.append(None)
                continue
            future_close = float(candles[index + horizon].close)
            current_close = float(candle.close)
            values.append((future_close - current_close) / current_close)

        column = TargetColumn(
            name=name,
            label=f"Next Return ({horizon})",
            description=f"Fractional price change {horizon} candle(s) ahead.",
            dtype="float",
        )
        return TargetOutput(series=[TargetSeries(column=column, values=values)])
