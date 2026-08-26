"""Next closing price — the raw future price, `horizon` candles ahead."""

from app.ml_datasets.base import (
    TargetColumn,
    TargetContext,
    TargetGenerator,
    TargetMetadata,
    TargetOutput,
    TargetSeries,
)
from app.ml_datasets.registry import register
from app.ml_datasets.targets.common import HORIZON_PARAMETER, shifted_column


@register
class NextClosePrice(TargetGenerator):
    """The raw closing price `horizon` candles after each row.

    The simplest possible target: no transformation, no normalization —
    just next-candle-ahead `close`. Useful as a baseline and as the input
    to any downstream transform (a researcher who wants percent-return can
    derive it from this and the row's own `close`, already present in the
    `ohlcv` feature).
    """

    metadata = TargetMetadata(
        name="next_close",
        label="Next Closing Price",
        description="The raw closing price `horizon` candles ahead of each row.",
        category="price",
        parameters=(HORIZON_PARAMETER,),
        outputs=("next_close_{horizon}",),
        value_type="float",
        is_deterministic=True,
    )

    def generate(self, ctx: TargetContext) -> TargetOutput:
        horizon = ctx.int_param("horizon")
        candles = ctx.candles
        name = f"next_close_{horizon}"
        values = shifted_column(candles, horizon, lambda candle: float(candle.close))
        column = TargetColumn(
            name=name,
            label=f"Next Close ({horizon})",
            description=f"Closing price {horizon} candle(s) ahead.",
            dtype="float",
        )
        return TargetOutput(series=[TargetSeries(column=column, values=values)])
