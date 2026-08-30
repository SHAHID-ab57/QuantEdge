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
    body: '"Placeholder Model" fabricates deterministic metrics and trains nothing real. "Logistic Regression" and "Linear Regression" are real scikit-learn baselines every advanced model must outperform — they need a market/timeframe to actually train on.',
  },
  {
    heading: 'Acceptable values',
    body: 'Any adapter from the catalogue below. Future TensorFlow and PyTorch integrations will register here and appear in this same list with no other change.',
  },
  {
    heading: 'Where the value comes from',
    body: 'GET /training-jobs/models — never free text, so an unregistered name can never be submitted.',
  },
];

export const SYMBOL_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'The market this job loads real candles from to build a training matrix.',
  },
  {
    heading: 'Why it matters',
    body: 'A real model adapter (one whose "requires real data" is true) has nothing to fit without it — the placeholder adapter ignores this field entirely.',
  },
  {
    heading: 'Acceptable values',
    body: 'Any market this platform already tracks candles for.',
  },
  {
    heading: 'Where the value comes from',
    body: 'GET /markets — the same catalogue the Markets and History pages use.',
  },
];

export const TIMEFRAME_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'The candle timeframe (e.g. 1h) to load from the selected market.',
  },
  {
    heading: 'Why it matters',
    body: 'Required alongside Symbol for a real model adapter — features and targets are computed over candles of exactly this timeframe.',
  },
  {
    heading: 'Acceptable values',
    body: 'Any timeframe this market actually has stored candles for.',
  },
  {
    heading: 'Where the value comes from',
    body: 'GET /markets/{symbol}/timeframes, once a market is selected.',
  },
];

export const TARGET_COLUMN_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: "Which built target column this job predicts, when the experiment's target_config produced more than one.",
  },
  {
    heading: 'Why it matters',
    body: 'A regression adapter needs a numeric target (e.g. next_close); a classification adapter needs a categorical one (e.g. next_direction) — the wrong pairing fails the job with a clear error.',
  },
  {
    heading: 'Acceptable values',
    body: 'Optional. Leave blank to use the first target column the dataset build produces.',
  },
];

export const NORMALIZE_FEATURES_FIELD_HELP: InfoTooltipSection[] = [
  {
    heading: 'What it is',
    body: 'Z-score normalizes every numeric feature column (mean/std fit on the train split alone) before the model trains or predicts.',
  },
  {
    heading: 'Why it matters',
    body: 'Without it, Feature Importance is scale-biased — a feature measured in the thousands (close, sma_20) shows a smaller coefficient than an equally predictive feature measured in single digits (candle_body), purely from scale, and L2 regularization (C) implicitly under-penalizes large-magnitude features for the same reason.',
  },
  {
    heading: 'Acceptable values',
    body: 'On by default for both real baseline adapters (Logistic Regression, Linear Regression) — both are scale-sensitive. Has no effect on the Placeholder Model, which never sees a real feature matrix.',
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
