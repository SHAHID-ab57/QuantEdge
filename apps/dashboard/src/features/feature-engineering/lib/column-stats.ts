import type { FeatureCell } from '@/types/api/features';

export interface ColumnStats {
  /** Total values inspected, including nulls. */
  count: number;
  nullCount: number;
  min: number | null;
  max: number | null;
  mean: number | null;
  std: number | null;
}

/**
 * Summary statistics for one column's values.
 *
 * Non-numeric cells (strings, booleans) are silently excluded from
 * min/max/mean/std rather than coerced — a categorical column's "average"
 * is meaningless, and `isNumericDtype` is what a caller should check
 * before deciding whether to show this at all. Nulls are counted
 * separately, since a null is a data-quality signal, not an outlier.
 */
export function computeColumnStats(values: readonly FeatureCell[]): ColumnStats {
  let nullCount = 0;
  const numbers: number[] = [];
  for (const value of values) {
    if (value === null || value === undefined) {
      nullCount += 1;
      continue;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      numbers.push(value);
    }
  }

  if (numbers.length === 0) {
    return { count: values.length, nullCount, min: null, max: null, mean: null, std: null };
  }

  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  const mean = numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
  const variance = numbers.reduce((sum, value) => sum + (value - mean) ** 2, 0) / numbers.length;

  return { count: values.length, nullCount, min, max, mean, std: Math.sqrt(variance) };
}

/** Whether a column's declared dtype is numeric — the gate for offering statistics on it at all. */
export function isNumericDtype(dtype: string): boolean {
  return dtype === 'float' || dtype === 'int';
}
