import type { TargetDTO } from '@/types/api/ml-datasets';

/**
 * A target's `value_type` is a free-form string on the wire (see
 * `app/ml_datasets/base.py`'s `TargetMetadata.value_type`), but every
 * builtin target today publishes either `"float"` or `"categorical"`.
 * This maps that backend vocabulary onto the ML-modelling vocabulary a
 * researcher actually thinks in — a categorical target is something a
 * classifier predicts, a float target is something a regressor predicts —
 * without inventing a new backend field for what is really just a
 * relabeling of `value_type` for the UI.
 */
export type TargetProblemType = 'classification' | 'regression';

export function targetProblemType(target: Pick<TargetDTO, 'value_type'>): TargetProblemType {
  return target.value_type === 'categorical' ? 'classification' : 'regression';
}

export function targetProblemTypeLabel(target: Pick<TargetDTO, 'value_type'>): string {
  return targetProblemType(target) === 'classification' ? 'Classification' : 'Regression';
}

/** A short, human phrase describing a target's valid horizon range, from its own `horizon` parameter spec. */
export function horizonRangeText(target: TargetDTO): string {
  const spec = target.parameters.find((parameter) => parameter.name === 'horizon');
  if (!spec) {
    return `Fixed at ${target.default_horizon} candle${target.default_horizon === 1 ? '' : 's'} ahead`;
  }
  const min = spec.minimum ?? 1;
  const max = spec.maximum;
  return max === null || max === undefined
    ? `Horizon ${min}+ candles ahead`
    : `Horizon ${min}–${max} candles ahead`;
}
