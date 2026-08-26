/**
 * Pure validation for a train/validation/test split configuration —
 * mirrors the backend's own `ChronologicalSplitter._validate_ratios`
 * tolerance so a researcher sees the same verdict client-side that the
 * server would otherwise reject the request for.
 */

const RATIO_TOLERANCE = 1e-6;

export interface SplitRatioValues {
  train: number;
  validation: number;
  test: number;
}

/** `null` when the ratios are usable; otherwise the reason they are not. */
export function validateSplitRatios(values: SplitRatioValues): string | null {
  const { train, validation, test } = values;
  if ([train, validation, test].some((value) => !Number.isFinite(value) || value < 0)) {
    return 'Each ratio must be zero or greater.';
  }
  if (train <= 0) {
    return 'The train ratio must be greater than zero.';
  }
  const sum = train + validation + test;
  if (Math.abs(sum - 1.0) > RATIO_TOLERANCE) {
    return `Ratios must sum to 1.0 (currently ${sum.toFixed(4)}).`;
  }
  return null;
}
