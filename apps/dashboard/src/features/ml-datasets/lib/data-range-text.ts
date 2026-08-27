import { RANGE_PRESET_LABELS } from '@/features/history/lib/resolve-range';
import type { DatasetFormValues } from '@/features/feature-engineering/components/dataset-form';

/** A human-readable rendering of the submitted date range — not carried by any build response, since the backend only ever sees resolved ISO bounds. */
export function dataRangeText(values: Pick<DatasetFormValues, 'range' | 'start' | 'end'>): string {
  if (values.range === 'custom') {
    if (!values.start || !values.end) {
      return 'Custom range (incomplete)';
    }
    return `${values.start} – ${values.end}`;
  }
  return RANGE_PRESET_LABELS[values.range];
}

/**
 * A human-readable date range derived from a build's own `timestamps`,
 * rather than the submitted form values — used for a reopened Dataset
 * History entry, which no longer has the original form's "range preset"
 * choice available, only the resolved rows it produced.
 */
export function historicalRangeText(timestamps: readonly string[]): string {
  const firstTimestamp = timestamps[0];
  const lastTimestamp = timestamps[timestamps.length - 1];
  if (!firstTimestamp || !lastTimestamp) {
    return 'No rows';
  }
  const first = new Date(firstTimestamp).toLocaleDateString();
  const last = new Date(lastTimestamp).toLocaleDateString();
  return first === last ? first : `${first} – ${last}`;
}
