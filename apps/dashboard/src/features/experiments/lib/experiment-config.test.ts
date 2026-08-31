import { describe, expect, it } from 'vitest';
import type { Experiment } from '@/types/api/experiments';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';
import {
  DEFAULT_EXPERIMENT_SPLIT,
  buildExperimentConfigPatch,
  datasetBuildToConfig,
  experimentToFeatureSelections,
  experimentToSplitValues,
  experimentToTargetSelections,
} from './experiment-config';

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

describe('experimentToFeatureSelections', () => {
  it('is empty for an experiment with nothing recorded', () => {
    expect(experimentToFeatureSelections(baseExperiment())).toEqual([]);
  });

  it('round-trips an existing feature_set', () => {
    const experiment = baseExperiment({
      feature_set: [
        { feature: 'sma', params: { period: '20' } },
        { feature: 'ohlcv', params: {} },
      ],
    });
    expect(experimentToFeatureSelections(experiment)).toEqual([
      { feature: 'sma', params: { period: '20' } },
      { feature: 'ohlcv', params: {} },
    ]);
  });
});

describe('experimentToTargetSelections', () => {
  it('is empty for an experiment with nothing recorded', () => {
    expect(experimentToTargetSelections(baseExperiment())).toEqual([]);
  });

  it('round-trips an existing target_config', () => {
    const experiment = baseExperiment({
      target_config: [{ target: 'next_close', params: { horizon: '3' } }],
    });
    expect(experimentToTargetSelections(experiment)).toEqual([
      { target: 'next_close', params: { horizon: '3' } },
    ]);
  });
});

describe('experimentToSplitValues', () => {
  it('falls back to the default split when nothing is recorded', () => {
    expect(experimentToSplitValues(baseExperiment())).toEqual(DEFAULT_EXPERIMENT_SPLIT);
  });

  it('round-trips an existing split_config', () => {
    const experiment = baseExperiment({
      split_config: { train: 0.8, validation: 0.1, test: 0.1 },
    });
    expect(experimentToSplitValues(experiment)).toEqual({ train: 0.8, validation: 0.1, test: 0.1 });
  });
});

describe('buildExperimentConfigPatch', () => {
  it('produces the exact PATCH body shape', () => {
    const patch = buildExperimentConfigPatch(
      [{ feature: 'sma', params: { period: '20' } }],
      [{ target: 'next_close', params: { horizon: '1' } }],
      { train: 0.7, validation: 0.15, test: 0.15 },
    );
    expect(patch).toEqual({
      feature_set: [{ feature: 'sma', params: { period: '20' } }],
      target_config: [{ target: 'next_close', params: { horizon: '1' } }],
      split_config: { train: 0.7, validation: 0.15, test: 0.15 },
    });
  });

  it('round-trips a full experiment through experimentTo*/buildExperimentConfigPatch unchanged', () => {
    const experiment = baseExperiment({
      feature_set: [{ feature: 'sma', params: { period: '20' } }],
      target_config: [{ target: 'next_direction', params: { horizon: '5' } }],
      split_config: { train: 0.6, validation: 0.2, test: 0.2 },
    });

    const patch = buildExperimentConfigPatch(
      experimentToFeatureSelections(experiment),
      experimentToTargetSelections(experiment),
      experimentToSplitValues(experiment),
    );

    expect(patch).toEqual({
      feature_set: experiment.feature_set,
      target_config: experiment.target_config,
      split_config: experiment.split_config,
    });
  });
});

function mlDatasetResponse(overrides: Partial<MLDatasetResponse> = {}): MLDatasetResponse {
  return {
    ml_dataset_id: 'ml-1',
    dataset_id: 'ds-1',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [],
    feature_columns: [],
    target_columns: [],
    timestamps: [],
    rows: [],
    split: [],
    features: [],
    targets: [],
    target_failures: [],
    split_ratios: { train: 0.7, validation: 0.15, test: 0.15 },
    split_bounds: { train_rows: 0, validation_rows: 0, test_rows: 0 },
    quality: {
      total_rows: 0,
      rows_returned: 0,
      rows_removed: 0,
      null_counts: {},
      duplicate_timestamps: 0,
      missing_candles: 0,
      feature_failures: [],
      generation_time_ms: 0,
    },
    validation: {
      dataset_id: 'ds-1',
      symbol: 'ETHUSD',
      timeframe: '1h',
      engine_version: '1.0.0',
      validated_at: '2026-01-01T00:00:00Z',
      passed: true,
      rules_run: [],
      summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
      categories: {},
      issues: [],
      rows: 0,
      columns: 0,
      duration_ms: 0,
    },
    meta: {
      row_count: 0,
      total_rows: 0,
      candles_analyzed: 0,
      rows_dropped_warmup: 0,
      rows_dropped_horizon: 0,
      warmup_candles: 0,
      max_horizon: 0,
      truncated: false,
      database_time_ms: 0,
      pipeline_version: '1.0.0',
      target_pipeline_version: '1.0.0',
      builder_version: '1.0.0',
      generated_at: '2026-01-01T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  };
}

describe('datasetBuildToConfig', () => {
  it('pre-fills features, targets, and split from a dataset build payload', () => {
    const dataset = mlDatasetResponse({
      features: [
        {
          feature: 'sma',
          label: 'SMA',
          version: '1.0.0',
          parameters: { period: 20 },
          columns: ['sma_20'],
          warmup: 20,
          execution_time_ms: 1,
        },
      ],
      targets: [
        {
          target: 'next_direction',
          label: 'Next Direction',
          version: '1.0.0',
          parameters: { horizon: 3 },
          columns: ['next_direction_3'],
          horizon: 3,
          execution_time_ms: 1,
        },
      ],
      split_ratios: { train: 0.6, validation: 0.2, test: 0.2 },
    });

    const config = datasetBuildToConfig(dataset);

    expect(config.features).toEqual([{ feature: 'sma', params: { period: '20' } }]);
    expect(config.targets).toEqual([{ target: 'next_direction', params: { horizon: '3' } }]);
    expect(config.split).toEqual({ train: 0.6, validation: 0.2, test: 0.2 });
  });

  it('stringifies boolean and numeric parameter values alike', () => {
    const dataset = mlDatasetResponse({
      features: [
        {
          feature: 'candle_shape',
          label: 'Candle Shape',
          version: '1.0.0',
          parameters: { normalize: true, window: 5 },
          columns: ['candle_body'],
          warmup: 0,
          execution_time_ms: 1,
        },
      ],
    });

    const config = datasetBuildToConfig(dataset);

    expect(config.features[0]?.params).toEqual({ normalize: 'true', window: '5' });
  });

  it('is empty when the build recorded no features or targets', () => {
    const config = datasetBuildToConfig(mlDatasetResponse());
    expect(config.features).toEqual([]);
    expect(config.targets).toEqual([]);
  });
});
