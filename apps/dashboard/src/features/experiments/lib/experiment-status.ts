import type { ExperimentStatus } from '@/types/api/experiments';

/** MUI Chip `color` per experiment status, for a consistent glance-able list/detail view. */
export const STATUS_COLORS: Record<
  ExperimentStatus,
  'default' | 'info' | 'success' | 'error' | 'warning'
> = {
  draft: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
  archived: 'warning',
};

/**
 * Accepts a plain `string` (not just `ExperimentStatus`) because the
 * filter bar's status list comes from the backend's own
 * `ExperimentListResponse.statuses` — a `string[]`, so a status this
 * frontend doesn't otherwise model still renders a readable label instead
 * of a type error.
 */
export function statusLabel(status: string): string {
  return `${status.charAt(0).toUpperCase()}${status.slice(1)}`;
}
