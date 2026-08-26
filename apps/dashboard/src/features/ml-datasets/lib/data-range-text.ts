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
