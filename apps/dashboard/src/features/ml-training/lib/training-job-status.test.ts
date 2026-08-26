import { describe, expect, it } from 'vitest';
import { STAGE_ORDER, STATUS_COLORS, stageLabel, statusLabel } from './training-job-status';

describe('statusLabel', () => {
  it('capitalizes the first letter of a status', () => {
    expect(statusLabel('pending')).toBe('Pending');
    expect(statusLabel('running')).toBe('Running');
    expect(statusLabel('cancelled')).toBe('Cancelled');
  });

  it('accepts an arbitrary string, not just a known status', () => {
    expect(statusLabel('custom_status')).toBe('Custom_status');
  });
});

describe('STATUS_COLORS', () => {
  it('defines a color for every training job status', () => {
    expect(Object.keys(STATUS_COLORS).sort()).toEqual(
      ['cancelled', 'completed', 'failed', 'pending', 'running'].sort(),
    );
  });

  it('gives failed a distinct error color', () => {
    expect(STATUS_COLORS.failed).toBe('error');
  });
});

describe('stageLabel', () => {
  it('renders a dash for no stage', () => {
    expect(stageLabel(null)).toBe('—');
  });

  it('renders a human-readable label for every known stage', () => {
    expect(stageLabel('validate_dataset')).toBe('Dataset Validation');
    expect(stageLabel('execute_training')).toBe('Training');
    expect(stageLabel('update_experiment')).toBe('Experiment Updated');
  });

  it('falls back to a capitalized string for an unknown stage', () => {
    expect(stageLabel('some_future_stage')).toBe('Some_future_stage');
  });
});

describe('STAGE_ORDER', () => {
  it('lists all six pipeline stages in execution order', () => {
    expect(STAGE_ORDER.map((stage) => stage.key)).toEqual([
      'validate_dataset',
      'load_dataset',
      'initialize_model',
      'execute_training',
      'save_results',
      'update_experiment',
    ]);
  });
});
