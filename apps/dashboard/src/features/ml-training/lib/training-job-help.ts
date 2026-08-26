import type { InfoTooltipSection } from '@/components/info-tooltip';
import type { TrainingJobStatus } from '@/types/api/training';

/**
 * Every `InfoTooltip`'s content for the Training page, kept in one place so
 * the copy is consistent wherever a field appears twice (e.g. the create
 * dialog and the detail dialog both explain "Model type").
 */

export const EXPERIMENT_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'The existing experiment this training job trains for and reports back to.',
  },
  {
    heading: 'Why it matters',
    body: "Running this job updates that experiment's status, metrics, and artifacts — a job never exists on its own.",
  },
  {
    heading: 'Acceptable values',
    body: 'Any experiment already registered on the Experiments page. Required.',
  },
  {
    heading: 'Where the value comes from',
    body: "Search by name — this is a searchable dropdown over every experiment's own record.",
  },
];

export const DATASET_VERSION_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'The versioned dataset citation this job trains over.',
  },
  {
    heading: 'Why it matters',
    body: 'The pipeline refuses to run without one — a training job must know which dataset build it belongs to.',
  },
  {
    heading: 'Acceptable values',
    body: 'Any non-empty dataset identifier. Ideally one already produced and reviewed via the ML Dataset Builder and Dataset Validation pages.',
  },
  {
    heading: 'Where the value comes from',
    body: "Automatically populated from the selected experiment's own dataset_version — override only if this job intentionally trains over a different build.",
  },
];

export const MODEL_TYPE_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'Which registered model adapter runs this job.',
  },
  {
    heading: 'Why it matters',
    body: 'Only "Placeholder Model" is registered today — it fabricates deterministic metrics and trains nothing real, so this framework can be exercised before a real model exists.',
  },
  {
    heading: 'Acceptable values',
    body: 'Any adapter from the catalogue below. Future TensorFlow, PyTorch, and scikit-learn integrations will register here and appear in this same list with no other change.',
  },
  {
    heading: 'Where the value comes from',
    body: 'GET /training-jobs/models — never free text, so an unregistered name can never be submitted.',
  },
];

export const HYPERPARAMETERS_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'Configuration values passed verbatim to the selected model adapter.',
  },
  {
    heading: 'Why it matters',
    body: "The placeholder adapter reads epochs/learning_rate and ignores everything else, so today's values mostly exercise the pipeline rather than change a real outcome — a future real model will actually use them.",
  },
  {
    heading: 'Acceptable values',
    body: 'The five known fields below have sensible defaults and are validated as numbers; add any other name/value pair as a custom parameter.',
  },
];

export const TRAINING_STATUS_HELP: Record<TrainingJobStatus, InfoTooltipSection> = {
  pending: {
    heading: 'Pending',
    body: 'Registered but not yet executed. Press Run to start the pipeline.',
  },
  running: {
    heading: 'Running',
    body: 'The pipeline is currently executing. This call blocks until it finishes — no worker/queue service exists yet, so a run is normally near-instant.',
  },
  completed: {
    heading: 'Completed',
    body: 'Every pipeline stage finished; the linked experiment was updated with the fabricated metrics and artifact.',
  },
  failed: {
    heading: 'Failed',
    body: 'A stage raised before finishing — see the error message and the stage the timeline stopped at. The linked experiment was marked failed too.',
  },
  cancelled: {
    heading: 'Cancelled',
    body: 'Withdrawn before running (or while running). No experiment update occurs for a cancelled job.',
  },
};

export const TRAINING_STATUS_LEGEND: InfoTooltipSection[] = Object.values(TRAINING_STATUS_HELP);
