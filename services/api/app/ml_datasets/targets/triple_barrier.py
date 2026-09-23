"""Triple-barrier labeling — first-touch classification against a
symmetric price barrier.

Investigated for MODEL-QUALITY-T1 as a candidate replacement for
`next_direction`'s fixed-horizon labeling, after `next_direction` failed
five independent checks across this research thread
(`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`, `HORIZON_SWEEP_ASSESSMENT.md`,
`REGIME_WALKFORWARD_ASSESSMENT.md`, the funding/OI assessment, and the
regime-walkforward's own ROC-AUC surviving the drift-artifact removal).
The default barrier (5%) is this platform's own real risk convention
(`paper_trading_strategy_default_stop_loss_pct`), not a value chosen for
this target in isolation; the default vertical barrier (72h) is the
shortest of the settings checked in
`docs/research/TARGET_REDEFINITION_ASSESSMENT.md`'s own diagnostic that
kept the resulting label distribution genuinely three-way (32/32/35 up/
down/time_expired at 5%/72h, vs. 12/14/74 at 5%/24h — the diagnostic's own
"not 99% time expired" bar, applied honestly rather than assumed).
"""

from app.ml_datasets.base import (
    FeatureValue,
    ParameterSpec,
    TargetColumn,
    TargetContext,
    TargetGenerator,
    TargetMetadata,
    TargetOutput,
    TargetSeries,
)
from app.ml_datasets.registry import register

BARRIER_PCT_PARAMETER = ParameterSpec(
    name="barrier_pct",
    type="float",
    label="Barrier Width",
    description=(
        "Symmetric upper/lower barrier, as a fraction of this row's own close (0.05 = +/-5%)."
    ),
    default=0.05,
    minimum=0.001,
    maximum=0.5,
)

MAX_HOURS_PARAMETER = ParameterSpec(
    name="max_hours",
    type="int",
    label="Vertical Barrier (hours)",
    description=("Maximum candles to wait for a barrier touch before labeling 'time_expired'."),
    default=72,
    minimum=1,
    maximum=500,
)


@register
class TripleBarrier(TargetGenerator):
    """Whether price first touches an upper barrier, a lower barrier, or
    neither within `max_hours`, relative to this row's own close.

    A first-touch walk, not a fixed-horizon lookahead like `next_direction`
    — `generate` scans forward from each row until a barrier is touched or
    `max_hours` elapses. Ambiguous same-candle double-touches (both the
    high clears the upper barrier and the low clears the lower barrier
    within one future candle) are resolved by that candle's own open,
    which the price path must have crossed before either wick: closer to
    the upper barrier's own side is labeled 'up', otherwise 'down'.
    """

    metadata = TargetMetadata(
        name="triple_barrier",
        label="Triple-Barrier Label",
        description=(
            "First-touch classification: whether price reaches an upper "
            "barrier ('up'), a lower barrier ('down'), or neither within "
            "max_hours ('time_expired'), relative to this row's own close."
        ),
        category="direction",
        parameters=(BARRIER_PCT_PARAMETER, MAX_HOURS_PARAMETER),
        outputs=("triple_barrier_{barrier_pct}_{max_hours}",),
        value_type="categorical",
        is_deterministic=True,
    )

    def horizon(self, params: dict[str, object]) -> int:
        return int(params["max_hours"])  # type: ignore[arg-type]

    def generate(self, ctx: TargetContext) -> TargetOutput:
        barrier_pct = ctx.float_param("barrier_pct")
        max_hours = ctx.int_param("max_hours")
        candles = ctx.candles
        n = len(candles)
        name = f"triple_barrier_{barrier_pct}_{max_hours}"

        values: list[FeatureValue] = []
        boundary = n - max_hours
        for index in range(n):
            if index >= boundary:
                values.append(None)
                continue
            entry = candles[index].close
            upper = entry * (1 + barrier_pct)
            lower = entry * (1 - barrier_pct)
            label = "time_expired"
            for offset in range(index + 1, index + 1 + max_hours):
                future = candles[offset]
                hit_up = future.high >= upper
                hit_down = future.low <= lower
                if hit_up and hit_down:
                    label = "up" if future.open >= entry else "down"
                    break
                if hit_up:
                    label = "up"
                    break
                if hit_down:
                    label = "down"
                    break
            values.append(label)

        column = TargetColumn(
            name=name,
            label=f"Triple Barrier (+/-{barrier_pct * 100:.1f}%, {max_hours}h)",
            description=(
                f"First-touch label against a +/-{barrier_pct * 100:.1f}% price "
                f"barrier within {max_hours} hours of this row's own close."
            ),
            dtype="categorical",
        )
        return TargetOutput(series=[TargetSeries(column=column, values=values)])
