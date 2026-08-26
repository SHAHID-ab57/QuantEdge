import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';
import { MLDatasetMetadataPanel } from './ml-dataset-metadata-panel';

afterEach(() => cleanup());

function dataset(): MLDatasetResponse {
  return {
    ml_dataset_id: '22222222-2222-4222-8222-222222222222',
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [{ name: 'close', label: 'Close', description: '', dtype: 'float' }],
    feature_columns: ['close'],
    target_columns: ['next_close_1'],
    timestamps: ['2026-01-01T00:00:00Z'],
    rows: [[100]],
    split: ['train'],
    features: [
      {
        feature: 'ohlcv',
        label: 'OHLCV',
        version: '1.0.0',
        parameters: {},
        columns: ['close'],
        warmup: 0,
        execution_time_ms: 0.1,
      },
    ],
    targets: [
      {
        target: 'next_close',
        label: 'Next Close Price',
        version: '1.0.0',
        parameters: { horizon: 1 },
        columns: ['next_close_1'],
        horizon: 1,
        execution_time_ms: 0.2,
      },
    ],
    target_failures: [],
    split_ratios: { train: 0.7, validation: 0.15, test: 0.15 },
    split_bounds: { train_rows: 1, validation_rows: 0, test_rows: 0 },
    quality: {
      total_rows: 1,
      rows_returned: 1,
      rows_removed: 0,
      null_counts: {},
      duplicate_timestamps: 0,
      missing_candles: 0,
      feature_failures: [],
      generation_time_ms: 0.4,
    },
    validation: {
      dataset_id: '11111111-1111-4111-8111-111111111111',
      symbol: 'ETHUSD',
      timeframe: '1h',
      engine_version: '1.0.0',
      validated_at: '2026-01-01T02:00:00Z',
      passed: true,
      rules_run: ['no_nulls'],
      summary: { total_checks: 1, errors: 0, warnings: 0, info: 0 },
      categories: {},
      issues: [],
      rows: 1,
      columns: 1,
      duration_ms: 0.3,
    },
    meta: {
      row_count: 1,
      total_rows: 1,
      candles_analyzed: 2,
      rows_dropped_warmup: 0,
      rows_dropped_horizon: 1,
      warmup_candles: 0,
      max_horizon: 1,
      truncated: false,
      database_time_ms: 1.4,
      pipeline_version: '1.0.0',
      target_pipeline_version: '1.0.0',
      builder_version: '1.0.0',
      generated_at: '2026-01-01T02:00:00Z',
      created_at: '2026-01-01T02:00:00Z',
    },
  };
}

describe('MLDatasetMetadataPanel', () => {
  it('renders the dataset UUID, source market/timeframe, and generated timestamp', () => {
    render(
      <ThemeProvider theme={theme}>
        <MLDatasetMetadataPanel dataset={dataset()} dataRangeText="All History" />
      </ThemeProvider>,
    );
    expect(screen.getByText('22222222-2222-4222-8222-222222222222')).toBeInTheDocument();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('1h')).toBeInTheDocument();
    expect(screen.getByText('All History')).toBeInTheDocument();
    expect(screen.getByText('2026-01-01T02:00:00Z')).toBeInTheDocument();
  });

  it('shows the validation report id and engine version', () => {
    render(
      <ThemeProvider theme={theme}>
        <MLDatasetMetadataPanel dataset={dataset()} dataRangeText="All History" />
      </ThemeProvider>,
    );
    expect(screen.getByText('Validation Report ID')).toBeInTheDocument();
    expect(screen.getByText('Engine Version')).toBeInTheDocument();
    expect(screen.getAllByText('1.0.0').length).toBeGreaterThan(0);
  });

  it('lists the target generator and a fixed splitter name', () => {
    render(
      <ThemeProvider theme={theme}>
        <MLDatasetMetadataPanel dataset={dataset()} dataRangeText="All History" />
      </ThemeProvider>,
    );
    expect(screen.getByText('Next Close Price')).toBeInTheDocument();
    expect(screen.getByText('ChronologicalSplitter')).toBeInTheDocument();
  });

  it('lists the supported export formats', () => {
    render(
      <ThemeProvider theme={theme}>
        <MLDatasetMetadataPanel dataset={dataset()} dataRangeText="All History" />
      </ThemeProvider>,
    );
    expect(screen.getByText('CSV, JSON')).toBeInTheDocument();
  });

  it('shows "None" for the target generator when no targets were requested', () => {
    render(
      <ThemeProvider theme={theme}>
        <MLDatasetMetadataPanel
          dataset={{ ...dataset(), targets: [] }}
          dataRangeText="All History"
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('None')).toBeInTheDocument();
  });
});
