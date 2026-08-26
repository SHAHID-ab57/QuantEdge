/**
 * The five hyperparameter names this UI knows about — presented as
 * dedicated numeric fields with defaults, validation, and tooltips, rather
 * than the plain key/value list every other (custom) parameter still uses.
 * `PlaceholderModelAdapter` only reads `epochs`/`learning_rate` and ignores
 * the rest today (see `app/training/adapters/placeholder.py`); all five are
 * offered here because a future real model adapter is expected to read
 * every one of them.
 */

export interface HyperparameterSpec {
  key: string;
  label: string;
  help: string;
  default: number;
  min: number;
  /** Whether the value must be a whole number. */
  integer: boolean;
  step?: number;
}

export const KNOWN_HYPERPARAMETER_SPECS: HyperparameterSpec[] = [
  {
    key: 'epochs',
    label: 'Epochs',
    help: 'How many full passes over the training data to run. Whole number, at least 1.',
    default: 10,
    min: 1,
    integer: true,
  },
  {
    key: 'learning_rate',
    label: 'Learning rate',
    help: 'How large a step the optimizer takes per update. Must be greater than 0 — typical values are small (e.g. 0.001–0.1).',
    default: 0.001,
    min: 0,
    integer: false,
    step: 0.001,
  },
  {
    key: 'batch_size',
    label: 'Batch size',
    help: 'How many training examples are processed together per step. Whole number, at least 1.',
    default: 32,
    min: 1,
    integer: true,
  },
  {
    key: 'random_seed',
    label: 'Random seed',
    help: 'Fixes randomness so a run can be reproduced exactly. Whole number, zero or greater.',
    default: 42,
    min: 0,
    integer: true,
  },
  {
    key: 'validation_frequency',
    label: 'Validation frequency',
    help: 'How often (in epochs) to evaluate against the validation split. Whole number, at least 1.',
    default: 1,
    min: 1,
    integer: true,
  },
];

export const KNOWN_HYPERPARAMETER_KEYS = new Set(
  KNOWN_HYPERPARAMETER_SPECS.map((spec) => spec.key),
);

/** `null` means valid; otherwise the message to show under the field. */
export function validateHyperparameterValue(spec: HyperparameterSpec, raw: string): string | null {
  if (raw.trim() === '') return null; // empty means "omit this parameter" — not an error
  const value = Number(raw);
  if (Number.isNaN(value)) return 'Must be a number.';
  if (spec.integer && !Number.isInteger(value)) return 'Must be a whole number.';
  if (value < spec.min) return `Must be ${spec.min} or greater.`;
  return null;
}
