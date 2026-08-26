import type { TrainingJobStage, TrainingJobStatus } from '@/types/api/training';

/** MUI Chip `color` per job status, mirroring `experiment-status.ts`'s own convention. */
export const STATUS_COLORS: Record<
  TrainingJobStatus,
  'default' | 'info' | 'success' | 'error' | 'warning'
> = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

/** Accepts a plain `string` so a status this frontend doesn't model still renders readably. */
export function statusLabel(status: string): string {
  return `${status.charAt(0).toUpperCase()}${status.slice(1)}`;
}

/** The six pipeline stages, in execution order, with the one label each is known
 * by everywhere in this feature (log stage badges, the status timeline) — a
 * single source of truth so the wording never drifts between the two. */
export const STAGE_ORDER: { key: TrainingJobStage; label: string }[] = [
  { key: 'validate_dataset', label: 'Dataset Validation' },
  { key: 'load_dataset', label: 'Dataset Loaded' },
  { key: 'initialize_model', label: 'Model Initialized' },
  { key: 'execute_training', label: 'Training' },
  { key: 'save_results', label: 'Saving Results' },
  { key: 'update_experiment', label: 'Experiment Updated' },
];

const STAGE_LABELS: Record<TrainingJobStage, string> = Object.fromEntries(
  STAGE_ORDER.map((stage) => [stage.key, stage.label]),
) as Record<TrainingJobStage, string>;

export function stageLabel(stage: string | null): string {
  if (stage === null) return '—';
  return STAGE_LABELS[stage as TrainingJobStage] ?? statusLabel(stage);
}
