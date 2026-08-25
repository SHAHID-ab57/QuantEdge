import { resolveRange, type RangePreset } from '@/features/history/lib/resolve-range';

const DAY_MS = 86_400_000;

export interface DatasetRangeValues {
  range: RangePreset;
  start: string;
  end: string;
}

/**
 * Convert a dataset form's range preset (or custom start/end) into the
 * half-open UTC bounds the API expects — the end day is included in full,
 * so "1st to 2nd" covers both days entirely.
 *
 * Promoted out of the Feature Engineering page's own local `toRange` once
 * the Dataset Validation page needed the identical conversion: both pages
 * let a researcher pick "Last 7 Days" or a custom date pair to build a
 * dataset from, and what that means must not be defined twice.
 */
export function toDatasetRange(values: DatasetRangeValues): { start?: string; end?: string } {
  if (values.range === 'custom') {
    if (!values.start || !values.end) {
      return {};
    }
    const end = new Date(new Date(`${values.end}T00:00:00Z`).getTime() + DAY_MS)
      .toISOString()
      .replace(/\.\d{3}Z$/, 'Z');
    return { start: `${values.start}T00:00:00Z`, end };
  }
  const resolved = resolveRange(values.range);
  return { start: resolved.start ?? undefined, end: resolved.end ?? undefined };
}
