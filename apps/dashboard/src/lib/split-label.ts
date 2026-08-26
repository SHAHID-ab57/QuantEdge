/**
 * The train/validation/test split vocabulary shared by every place that
 * renders a per-row or per-segment split label — the ML Dataset Builder's
 * preview column, its timeline visualization, and its export summary.
 * Promoted to a top-level `lib` module (rather than living inside either
 * `feature-engineering/` or `ml-datasets/`) because `dataset-preview-table.tsx`
 * — owned by `feature-engineering/` — renders this same vocabulary for the
 * ML Dataset Builder's benefit, and neither module should have to import
 * the other just to agree on what "train" is labeled or colored.
 */

export const SPLIT_LABELS = ['train', 'validation', 'test'] as const;

export type SplitLabel = (typeof SPLIT_LABELS)[number];

export function isSplitLabel(value: string): value is SplitLabel {
  return (SPLIT_LABELS as readonly string[]).includes(value);
}

/** MUI Chip `color` per split — train is neutral, validation/test read as distinct at a glance. */
export const SPLIT_COLORS: Record<SplitLabel, 'default' | 'info' | 'warning'> = {
  train: 'default',
  validation: 'info',
  test: 'warning',
};

export function splitLabelText(label: string): string {
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}`;
}
