"""Shared parameter spec and shifting helper for the builtin targets.

Promoted here once every builtin target needed the identical `horizon`
parameter and the identical "look `horizon` candles ahead, `None` past the
end" shifting logic — the same "factor out the shared piece once a second
generator needs it" discipline `app/indicators/builtin/common.py` already
established for SMA/EMA/WMA's shared parameter/warmup helpers.
"""

from collections.abc import Callable, Sequence

from app.ml_datasets.base import FeatureValue, OHLCVPoint, ParameterSpec

#: Every builtin target accepts this exact parameter — declared once so
#: "how many candles ahead" means the same thing, with the same bounds and
#: the same default, everywhere it appears.
HORIZON_PARAMETER = ParameterSpec(
    name="horizon",
    type="int",
    label="Horizon",
    description="How many candles ahead the target looks.",
    default=1,
    minimum=1,
    maximum=500,
)


def shifted_column(
    candles: Sequence[OHLCVPoint],
    horizon: int,
    compute: Callable[[OHLCVPoint], FeatureValue],
) -> list[FeatureValue]:
    """Compute one value per row from the candle `horizon` positions ahead.

    Row `i` gets `compute(candles[i + horizon])`; the trailing `horizon`
    rows (which have no candle that far ahead) get `None` — the forward-
    looking mirror of a feature's warmup, and the exact contract
    `TargetPipeline._verify_forward_looking_contract` enforces every
    builtin target against.
    """
    count = len(candles)
    boundary = count - horizon
    values: list[FeatureValue] = []
    for index in range(count):
        if index < boundary:
            values.append(compute(candles[index + horizon]))
        else:
            values.append(None)
    return values
