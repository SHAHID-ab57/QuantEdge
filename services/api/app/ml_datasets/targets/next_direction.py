"""Next candle direction — a categorical up/down/flat label, `horizon` candles ahead."""

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
class NextDirection(TargetGenerator):
    """Whether the close `horizon` candles ahead is higher, lower, or unchanged.

    A classification target (`"up"` / `"down"` / `"flat"`) for a model
    that predicts direction rather than magnitude — the categorical
    counterpart to `next_return`'s continuous value. Declared
    `value_type="categorical"` so a consumer (a one-hot encoder, a preview
    table) treats it the way `candle_shape`'s own `candle_direction`
    feature column already is.
    """

    metadata = TargetMetadata(
        name="next_direction",
        label="Next Candle Direction",
        description=(
            "Whether the close `horizon` candles ahead is higher ('up'), lower "
            "('down'), or unchanged ('flat') relative to this row's close."
        ),
        category="direction",
        parameters=(HORIZON_PARAMETER,),
        outputs=("next_direction_{horizon}",),
        value_type="categorical",
        is_deterministic=True,
    )

    def generate(self, ctx: TargetContext) -> TargetOutput:
        horizon = ctx.int_param("horizon")
        candles = ctx.candles
        name = f"next_direction_{horizon}"

        values = []
        boundary = len(candles) - horizon
        for index, candle in enumerate(candles):
            if index >= boundary:
                values.append(None)
                continue
            future_close = float(candles[index + horizon].close)
            current_close = float(candle.close)
            if future_close > current_close:
                values.append("up")
            elif future_close < current_close:
                values.append("down")
            else:
                values.append("flat")

        column = TargetColumn(
            name=name,
            label=f"Next Direction ({horizon})",
            description=f"Direction of price change {horizon} candle(s) ahead.",
            dtype="categorical",
        )
        return TargetOutput(series=[TargetSeries(column=column, values=values)])
