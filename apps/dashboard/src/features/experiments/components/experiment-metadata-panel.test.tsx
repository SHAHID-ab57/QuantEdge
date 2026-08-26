import { describe, expect, it } from 'vitest';
import type { Experiment } from '@/types/api/experiments';
import {
  describeFeatureSet,
  describePredictionHorizon,
  describeSplitConfig,
  describeTargetConfig,
} from './experiment-metadata-panel';

function baseExperiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: 'exp-1',
    name: 'baseline',
    dataset_version: null,
    feature_set: null,
    target_config: null,
    split_config: null,
    model_type: null,
    status: 'draft',
    notes: null,
    tags: [],
    metrics: [],
    artifacts: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('describeFeatureSet', () => {
  it('reports not recorded when empty', () => {
    expect(describeFeatureSet(baseExperiment())).toBe('Not recorded');
  });

  it('joins feature names', () => {
    const experiment = baseExperiment({
      feature_set: [
        { feature: 'sma', params: {} },
        { feature: 'ema', params: {} },
      ],
    });
    expect(describeFeatureSet(experiment)).toBe('sma, ema');
  });
});

describe('describeTargetConfig', () => {
  it('reports not recorded when empty', () => {
    expect(describeTargetConfig(baseExperiment())).toBe('Not recorded');
  });

  it('joins target names', () => {
    const experiment = baseExperiment({ target_config: [{ target: 'next_close', params: {} }] });
    expect(describeTargetConfig(experiment)).toBe('next_close');
  });
});

describe('describeSplitConfig', () => {
  it('reports not recorded when absent', () => {
    expect(describeSplitConfig(baseExperiment())).toBe('Not recorded');
  });

  it('formats train/validation/test as percentages', () => {
    const experiment = baseExperiment({
      split_config: { train: 0.7, validation: 0.15, test: 0.15 },
    });
    expect(describeSplitConfig(experiment)).toBe('70% / 15% / 15%');
  });
});

describe('describePredictionHorizon', () => {
  it('returns null when no target declares a horizon', () => {
    const experiment = baseExperiment({ target_config: [{ target: 'next_close', params: {} }] });
    expect(describePredictionHorizon(experiment)).toBeNull();
  });

  it('returns null when there is no target config at all', () => {
    expect(describePredictionHorizon(baseExperiment())).toBeNull();
  });

  it('returns the first horizon found', () => {
    const experiment = baseExperiment({
      target_config: [
        { target: 'next_close', params: { horizon: '3' } },
        { target: 'next_direction', params: { horizon: '5' } },
      ],
    });
    expect(describePredictionHorizon(experiment)).toBe('3');
  });
});
